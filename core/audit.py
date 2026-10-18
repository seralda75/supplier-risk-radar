"""Auditoría en SQLite: cada decisión queda registrada con su evidencia (trazabilidad GxP).

Patrón tomado de core/agent.py del kit: tabla append-only con el resultado completo en JSON.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

from .config import DB_PATH


def _db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS assessments (
        id INTEGER PRIMARY KEY, ts TEXT, news_id TEXT, headline TEXT, mode TEXT, model TEXT,
        is_risk INTEGER, urgent INTEGER, affected_ids TEXT, event_type TEXT, severity INTEGER,
        confidence REAL, needs_review INTEGER, payload TEXT)""")
    # Migración: las bases creadas antes de la v3 no tienen la columna de consenso
    cols = {row[1] for row in con.execute("PRAGMA table_info(assessments)")}
    if "consensus" not in cols:
        con.execute("ALTER TABLE assessments ADD COLUMN consensus INTEGER")   # 1 / 0 / NULL (modo reglas)
    return con


def log(result) -> None:
    """Registra un resultado de pipeline.assess() (objeto con model_dump())."""
    r = result.model_dump()
    with _db() as con:
        con.execute(
            "INSERT INTO assessments (ts, news_id, headline, mode, model, is_risk, urgent, affected_ids, "
            "event_type, severity, confidence, needs_review, consensus, payload) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), r["news_id"], r["headline"], r["mode"], r["model"],
             int(r["is_risk"]), int(r["urgent"]), "; ".join(r["affected_ids"]), r["event_type"], r["severity"],
             r["confidence"], int(r["needs_review"]),
             None if r.get("consensus") is None else int(r["consensus"]), json.dumps(r, ensure_ascii=False, default=str)))


def history(limit: int = 500):
    import pandas as pd
    with _db() as con:
        return pd.read_sql("SELECT id, ts, news_id, headline, mode, model, is_risk, urgent, affected_ids, "
                           "event_type, severity, confidence, needs_review, consensus FROM assessments "
                           f"ORDER BY id DESC LIMIT {int(limit)}", con)
