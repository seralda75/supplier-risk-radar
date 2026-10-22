"""Configuración del bot. El token se lee de .env (python-dotenv) y nunca se imprime ni se guarda en logs."""
from __future__ import annotations

import logging
import os
import sqlite3

from dotenv import load_dotenv

from core import demo, feedback, subscriptions, tasks
from core.config import ROOT

load_dotenv(ROOT / ".env")

# El panel en local. Los enlaces «Ver en el panel» abren la alerta (?alert=<id>, y ?demo=1 en modo demo)
PANEL_URL = os.getenv("PANEL_URL", "http://localhost:8501").rstrip("/")


def token() -> str:
    """El token del bot ('' si no está configurado)."""
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def redact(text: str) -> str:
    """Tapa el token si aparece en un texto (mensajes de error con la URL de la API)."""
    t = token()
    return text.replace(t, "<token>") if t else text


class RedactToken(logging.Filter):
    """Filtro de logging: ningún registro sale con el token."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def connect(is_demo: bool) -> sqlite3.Connection:
    """La misma SQLite que el panel: data/demo.db en modo demo, data/app.db si no."""
    if is_demo:
        return demo.connect()
    return subscriptions.ensure(tasks.ensure(feedback.connect()))


def panel_link(news_id: str, is_demo: bool) -> str:
    return f"{PANEL_URL}/?{'demo=1&' if is_demo else ''}alert={news_id}"
