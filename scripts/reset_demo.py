"""Deja la demo limpia sin borrar nada importante.

    python scripts/reset_demo.py            # vacía data/demo.db (todo lo hecho en «Modo demo»)
    python scripts/reset_demo.py --panel    # además, las pruebas hechas fuera del modo demo en data/app.db:
                                            # decisiones, pedidos, recordatorios, comunicaciones y avisos

Los chats de Telegram registrados se conservan (sus suscripciones automáticas se recrean solas).

Nunca toca la auditoría del pipeline (tabla assessments de app.db), los resultados (data/results), la
entrega (outputs/) ni la caché del LLM. Con --panel se guarda antes una copia: data/app.db.bak-<fecha>.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import demo, feedback                             # noqa: E402

# Los chats de Telegram registrados (tabla buyers) se conservan: no hay que volver a hacer /start
PANEL_TABLES = ("feedback", "orders", "reminders", "communications", "subscriptions", "notifications")


def clear(path: Path, tables: tuple[str, ...]) -> dict[str, int]:
    con = sqlite3.connect(path)
    existing = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    out = {}
    with con:
        for t in tables:
            if t in existing:
                out[t] = con.execute(f"DELETE FROM {t}").rowcount
    con.close()
    return out


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--panel", action="store_true", help="borra también las pruebas del panel en data/app.db")
    args = ap.parse_args()
    if demo.DB_PATH.exists():
        print(f"{demo.DB_PATH}: {clear(demo.DB_PATH, ('demo_news',) + PANEL_TABLES)}")
    else:
        print(f"{demo.DB_PATH}: no existe (nada que borrar)")
    if args.panel and feedback.DB_PATH.exists():
        backup = feedback.DB_PATH.with_name(f"app.db.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(feedback.DB_PATH, backup)
        print(f"copia de seguridad: {backup}")
        print(f"{feedback.DB_PATH}: {clear(feedback.DB_PATH, PANEL_TABLES)} (assessments se conserva)")


if __name__ == "__main__":
    main()
