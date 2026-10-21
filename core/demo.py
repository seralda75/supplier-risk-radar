"""Modo demo en directo: noticias que «llegan» una a una y se procesan con el pipeline real.

Las noticias salen de la validación (el jurado no las ha visto), en el orden de FEED: primero una urgente,
luego ruido que el sistema descarta, una alerta por ubicación sin nombre de proveedor, etc.
Cada noticia se procesa con assess():
- con Ollama: en directo (sin la caché del LLM) o con la caché, según el interruptor «IA en directo»;
- sin Ollama, o si la IA tarda más de LIVE_TIMEOUT_S: el resultado precalculado (data/results/validation.json).

Todo lo de la demo va a data/demo.db (decisiones, pedidos, recordatorios, comunicaciones y las noticias
inyectadas): no toca la entrega, los resultados guardados ni data/app.db. «Reiniciar demo» vacía demo.db.
assess() se llama con log=False: tampoco escribe en la auditoría del pipeline.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime

from . import feedback, results, tasks
from .config import DATA_DIR
from .data import load_news
from .feedback import _LOCK

DB_PATH = DATA_DIR / "demo.db"
# Guion de la demo (IDs de validación). No se usa para ajustar nada: solo decide el orden de llegada.
FEED = ["N008", "N019", "N041", "N022", "N056", "N051", "N044", "N027", "N032", "N034"]
LIVE_TIMEOUT_S = 60           # si la IA en directo tarda más, se usa el resultado precalculado
SPLIT = "test"                # las noticias de la demo se suman a la cola de las noticias de test

_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="demo")
_warm = threading.Event()


def ensure(con: sqlite3.Connection) -> sqlite3.Connection:
    """Tablas de la demo, además de las del panel (decisiones, pedidos, recordatorios, comunicaciones)."""
    tasks.ensure(con)
    with _LOCK, con:
        con.execute("""CREATE TABLE IF NOT EXISTS demo_news (
            seq INTEGER PRIMARY KEY, ts TEXT, news_id TEXT, mode TEXT, seconds REAL, result TEXT)""")
    return con


def connect(path=None) -> sqlite3.Connection:
    return ensure(feedback.connect(path or DB_PATH))


def injected(con: sqlite3.Connection) -> list[dict]:
    """Resultados de las noticias ya «recibidas», en orden de llegada."""
    with _LOCK:
        rows = con.execute("SELECT result FROM demo_news ORDER BY seq").fetchall()
    return [json.loads(r[0]) for r in rows]


def progress(con: sqlite3.Connection) -> tuple[int, int]:
    """(noticias recibidas, total del guion)."""
    return len(injected(con)), len(FEED)


def next_news(con: sqlite3.Connection) -> dict | None:
    """La siguiente noticia del guion (fila de validación, sin usar sus etiquetas), o None si se acabó."""
    done = {r["news_id"] for r in injected(con)}
    rows = {n["News_ID"]: n for n in load_news("validation")}
    nid = next((i for i in FEED if i not in done), None)
    if nid is None:
        return None
    n = rows[nid]
    return {k: n.get(k, "") for k in ("News_ID", "Published_Date", "Source", "Headline", "Summary")}


def precomputed(news_id: str) -> dict:
    """El resultado guardado de esa noticia (sin las etiquetas oficiales)."""
    d = results.load("validation") or {"results": []}
    r = next(x for x in d["results"] if x["news_id"] == news_id)
    return {k: v for k, v in r.items() if k != "gold"}


def start(news: dict, live: bool) -> Future:
    """Lanza el pipeline real en segundo plano (el panel muestra los pasos mientras tanto).
    live=True: sin la caché del LLM, una llamada real a Ollama."""
    from .pipeline import assess

    def run() -> dict:
        r = assess(news, use_llm=True, log=False, use_cache=not live).model_dump()
        r["summary"] = news.get("Summary", "")
        return r
    return _pool.submit(run)


def save(con: sqlite3.Connection, result: dict, mode: str, seconds: float) -> None:
    with _LOCK, con:
        con.execute("INSERT INTO demo_news (ts, news_id, mode, seconds, result) VALUES (?,?,?,?,?)",
                    (datetime.now().isoformat(timespec="seconds"), result["news_id"], mode, round(seconds, 2),
                     json.dumps(result, ensure_ascii=False, default=str)))


def reset(con: sqlite3.Connection) -> None:
    """Deja la demo como al principio: borra todo lo que hay en demo.db (y solo eso)."""
    with _LOCK, con:
        for table in ("demo_news", "feedback", "orders", "reminders", "communications"):
            con.execute(f"DELETE FROM {table}")


def warm_up() -> None:
    """Carga el modelo en la GPU en segundo plano al activar el modo demo: la primera noticia no paga
    el arranque en frío. Una sola vez por proceso."""
    if _warm.is_set():
        return
    _warm.set()

    def run() -> None:
        from . import llm
        try:
            if llm.is_up(timeout=1):
                llm.chat("OK", temperature=0)
                llm.embed(["warm up"])
                from .judge import build_prompt          # carga la base de ejemplos (Chroma)
                build_prompt("Supplier warm up", "", [], None)
        except Exception:          # calentar es opcional: si falla, la primera noticia tardará más
            pass
    _pool.submit(run)


def elapsed(t0: float) -> float:
    return time.perf_counter() - t0
