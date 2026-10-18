"""Respuesta de los compradores a cada alerta: confirmar o falsa alarma (SQLite).

La IA prepara la decisión y una persona la toma: cada respuesta queda registrada (quién, cuándo,
desde qué canal) y sirve para medir el sistema y añadir ejemplos nuevos en el futuro. La usan el
panel (fase 4) y, más adelante, los botones del bot de Telegram.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

from .config import DB_PATH

VERDICTS = {"confirmada": "Alerta confirmada", "falsa_alarma": "Falsa alarma"}


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY, ts TEXT, split TEXT, news_id TEXT, verdict TEXT,
        user TEXT, channel TEXT, note TEXT)""")
    return con


def save(split: str, news_id: str, verdict: str, user: str = "comprador", channel: str = "panel",
         note: str = "") -> None:
    if verdict not in VERDICTS:
        raise ValueError(f"Veredicto desconocido: {verdict}")
    with _db() as con:
        con.execute("INSERT INTO feedback (ts, split, news_id, verdict, user, channel, note) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (datetime.now().isoformat(timespec="seconds"), split, news_id, verdict, user, channel, note))


def latest(split: str) -> dict[str, dict]:
    """Última respuesta de cada noticia de un conjunto: {news_id: {verdict, user, ts, channel}}."""
    with _db() as con:
        rows = con.execute("SELECT news_id, verdict, user, ts, channel FROM feedback WHERE split = ? "
                           "ORDER BY id", (split,)).fetchall()
    return {r[0]: {"verdict": r[1], "user": r[2], "ts": r[3], "channel": r[4]} for r in rows}


def history(limit: int = 200) -> list[dict]:
    with _db() as con:
        rows = con.execute("SELECT ts, split, news_id, verdict, user, channel, note FROM feedback "
                           "ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
    return [dict(zip(["ts", "split", "news_id", "verdict", "user", "channel", "note"], r)) for r in rows]
