"""Cachés del panel: cada clic solo recalcula lo que cambia.

- st.cache_data: resultados guardados (JSON), alertas derivadas, ejemplos del simulador, documentos.
  La clave incluye la fecha de modificación del fichero: si se regenera, se vuelve a leer.
- st.cache_resource: la conexión a SQLite (una para todo el proceso): decisiones, pedidos y recordatorios.
- Ollama: se comprueba con un timeout corto y la respuesta vale 30 s; no se pregunta en cada clic.
- Modo demo (interruptor de la barra lateral): todo se lee y se escribe en data/demo.db, y las noticias
  «recibidas» en la demo se suman a las alertas de test. data/app.db y los resultados no se tocan.

El Excel de proveedores y materiales ya se lee una sola vez por proceso (lru_cache en
core/suppliers.py y core/scenario.py), porque también lo usan los scripts y el bot sin Streamlit.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import streamlit as st

from core import demo, feedback, llm, results, scenario, subscriptions, tasks
from core.config import ROOT

from .data import Alert, build_alerts

OLLAMA_TTL_S = 30
OLLAMA_TIMEOUT_S = 0.5
TELEGRAM_TTL_S = 60
TELEGRAM_TIMEOUT_S = 1.5


def _mtime(p: Path) -> float:
    return p.stat().st_mtime if p.exists() else 0.0


@st.cache_data(show_spinner=False)
def _results(split: str, mtime: float) -> dict | None:
    return results.load(split)


def data(split: str) -> dict | None:
    """Resultados guardados de un conjunto (data/results/<split>.json)."""
    return _results(split, _mtime(results.path(split)))


def all_data() -> dict[str, dict | None]:
    return {sp: data(sp) for sp in results.SPLITS}


@st.cache_data(show_spinner=False)
def _alerts(split: str, mtime: float) -> list[Alert]:
    d = results.load(split)
    return build_alerts(d["results"]) if d else []


@st.cache_data(show_spinner=False)
def _alerts_demo(split: str, mtime: float, injected: str) -> list[Alert]:
    d = results.load(split)
    return build_alerts((d["results"] if d else []) + json.loads(injected))


def demo_on() -> bool:
    return bool(st.session_state.get("demo"))


def alerts(split: str) -> list[Alert]:
    """Alertas de un conjunto; en modo demo, las de test más las de las noticias recibidas en la demo."""
    mtime = _mtime(results.path(split))
    if split == demo.SPLIT and demo_on():
        extra = demo.injected(db())
        if extra:
            return _alerts_demo(split, mtime, json.dumps(extra, ensure_ascii=False, sort_keys=True))
    return _alerts(split, mtime)


@st.cache_resource(show_spinner=False)
def _connection(path: str, is_demo: bool) -> sqlite3.Connection:
    return demo.connect(path) if is_demo else tasks.ensure(feedback.connect(path))


def db() -> sqlite3.Connection:
    """Conexión compartida a SQLite: data/app.db o, en modo demo, data/demo.db (la ruta forma parte de la
    clave: los tests usan bases temporales)."""
    if demo_on():
        return _connection(str(demo.DB_PATH), True)
    return _connection(str(feedback.DB_PATH), False)


def decisions(split: str) -> dict[str, dict]:
    """Decisiones vigentes de los compradores (no se cachea: cambian con cada clic)."""
    return feedback.active(split, db())


def items(split: str) -> list[dict]:
    """Pedidos y recordatorios creados desde las alertas (no se cachea: cambian con cada clic)."""
    return tasks.items(split, db())


@st.cache_data(ttl=OLLAMA_TTL_S, show_spinner=False)
def llm_up() -> bool:
    return llm.is_up(timeout=OLLAMA_TIMEOUT_S)


@st.cache_data(ttl=TELEGRAM_TTL_S, show_spinner=False)
def _telegram() -> tuple[bool, str]:
    try:
        from bot import notifier
        return notifier.status(timeout=TELEGRAM_TIMEOUT_S)
    except Exception:                     # sin las dependencias del bot: el panel funciona igual
        return False, "Telegram desactivado"


def telegram() -> tuple[bool, str]:
    """(activo, texto) para el pie del menú: «Telegram activo · @bot · 2 chats» o «Telegram desactivado (…)».
    Se comprueba con un timeout corto y la respuesta vale TELEGRAM_TTL_S: sin token o sin internet, el panel
    sigue igual."""
    ok, text = _telegram()
    if ok:
        n = len(subscriptions.chats(db()))
        text += f" · {n} chat{'s' if n != 1 else ''}"
    return ok, text


@st.cache_data(show_spinner=False)
def _examples(mtime: float) -> list[dict]:
    return scenario.load_examples()


def examples() -> list[dict]:
    return _examples(_mtime(scenario.EXAMPLES_PATH))


@st.cache_data(show_spinner=False)
def _doc(name: str, mtime: float) -> str:
    return (ROOT / "docs" / name).read_text(encoding="utf-8")


def doc(name: str) -> str:
    return _doc(name, _mtime(ROOT / "docs" / name))
