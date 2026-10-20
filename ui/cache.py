"""Cachés del panel: cada clic solo recalcula lo que cambia.

- st.cache_data: resultados guardados (JSON), alertas derivadas, ejemplos del simulador, documentos.
  La clave incluye la fecha de modificación del fichero: si se regenera, se vuelve a leer.
- st.cache_resource: la conexión a SQLite (una para todo el proceso).
- Ollama: se comprueba con un timeout corto y la respuesta vale 30 s; no se pregunta en cada clic.

El Excel de proveedores y materiales ya se lee una sola vez por proceso (lru_cache en
core/suppliers.py y core/scenario.py), porque también lo usan los scripts y el bot sin Streamlit.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import streamlit as st

from core import feedback, llm, results, scenario
from core.config import ROOT

from .data import Alert, build_alerts

OLLAMA_TTL_S = 30
OLLAMA_TIMEOUT_S = 0.5


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


def alerts(split: str) -> list[Alert]:
    return _alerts(split, _mtime(results.path(split)))


@st.cache_resource(show_spinner=False)
def _connection(path: str) -> sqlite3.Connection:
    return feedback.connect(path)


def db() -> sqlite3.Connection:
    """Conexión compartida a SQLite (la ruta forma parte de la clave: los tests usan una base temporal)."""
    return _connection(str(feedback.DB_PATH))


def decisions(split: str) -> dict[str, dict]:
    """Decisiones vigentes de los compradores (no se cachea: cambian con cada clic)."""
    return feedback.active(split, db())


@st.cache_data(ttl=OLLAMA_TTL_S, show_spinner=False)
def llm_up() -> bool:
    return llm.is_up(timeout=OLLAMA_TIMEOUT_S)


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
