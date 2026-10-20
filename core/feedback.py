"""Respuesta de los compradores a cada alerta: aprobar el plan o falsa alarma (SQLite).

La IA prepara la decisión y una persona la toma: cada respuesta queda registrada (quién, cuándo,
desde qué canal) y sirve para medir el sistema y añadir ejemplos nuevos en el futuro. La usan el
panel (fase 4) y, más adelante, los botones del bot de Telegram.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime

from .config import DB_PATH

# "plan_aprobado" lo registra el botón «Aprobar plan» del centro de control; "confirmada" se mantiene
# para las respuestas guardadas por versiones anteriores del panel. "reabierta" deshace la decisión
# anterior sin borrarla: la auditoría conserva las dos.
VERDICTS = {"plan_aprobado": "Plan aprobado", "confirmada": "Alerta confirmada", "falsa_alarma": "Falsa alarma",
            "reabierta": "Decisión reabierta"}
_LOCK = threading.Lock()         # una conexión compartida entre las sesiones del panel: escrituras en serie


def connect(path=None) -> sqlite3.Connection:
    """Conexión con la tabla creada. El panel la abre una vez y la comparte (st.cache_resource), así que
    se permite usarla desde varios hilos; las escrituras van protegidas con _LOCK."""
    con = sqlite3.connect(path or DB_PATH, check_same_thread=False)
    con.execute("""CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY, ts TEXT, split TEXT, news_id TEXT, verdict TEXT,
        user TEXT, channel TEXT, note TEXT)""")
    return con


def _db(con: sqlite3.Connection | None) -> sqlite3.Connection:
    return con if con is not None else connect()


def save(split: str, news_id: str, verdict: str, user: str = "comprador", channel: str = "panel",
         note: str = "", con: sqlite3.Connection | None = None) -> None:
    if verdict not in VERDICTS:
        raise ValueError(f"Veredicto desconocido: {verdict}")
    db = _db(con)
    with _LOCK, db:
        db.execute("INSERT INTO feedback (ts, split, news_id, verdict, user, channel, note) "
                   "VALUES (?,?,?,?,?,?,?)",
                   (datetime.now().isoformat(timespec="seconds"), split, news_id, verdict, user, channel, note))


def latest(split: str, con: sqlite3.Connection | None = None) -> dict[str, dict]:
    """Última respuesta de cada noticia de un conjunto: {news_id: {verdict, user, ts, channel}}."""
    with _LOCK:
        rows = _db(con).execute("SELECT news_id, verdict, user, ts, channel FROM feedback WHERE split = ? "
                                "ORDER BY id", (split,)).fetchall()
    return {r[0]: {"verdict": r[1], "user": r[2], "ts": r[3], "channel": r[4]} for r in rows}


def active(split: str, con: sqlite3.Connection | None = None) -> dict[str, dict]:
    """Decisiones vigentes: la última de cada noticia, salvo que se haya reabierto."""
    return {k: v for k, v in latest(split, con).items() if v["verdict"] != "reabierta"}


def history(limit: int = 200, con: sqlite3.Connection | None = None) -> list[dict]:
    with _LOCK:
        rows = _db(con).execute("SELECT ts, split, news_id, verdict, user, channel, note FROM feedback "
                                "ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    return [dict(zip(["ts", "split", "news_id", "verdict", "user", "channel", "note"], r)) for r in rows]
