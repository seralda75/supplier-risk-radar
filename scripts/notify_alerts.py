"""Avisa a los compradores de las alertas ya calculadas (data/results/<split>.json), sin llamar a la IA.

    python scripts/notify_alerts.py                 # alertas de test, con data/app.db
    python scripts/notify_alerts.py --demo          # con data/demo.db (como el «Modo demo»)
    python scripts/notify_alerts.py --dry-run       # solo dice a quién avisaría

Cada chat recibe cada alerta una sola vez (tabla notifications): se puede ejecutar varias veces. Las alertas
marcadas como falsa alarma no se avisan. El pipeline hace lo mismo con assess(..., notify="test").
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bot import config, notifier                            # noqa: E402
from core import feedback, results                          # noqa: E402
from core.labels import short_supplier                      # noqa: E402
from ui.data import build_alerts                            # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=list(results.SPLITS), default="test")
    ap.add_argument("--demo", action="store_true", help="usa data/demo.db")
    ap.add_argument("--dry-run", action="store_true", help="no envía ni registra nada")
    args = ap.parse_args()
    con = config.connect(args.demo)
    d = results.load(args.split)
    false_alarms = {k for k, v in feedback.active(args.split, con).items() if v["verdict"] == "falsa_alarma"}
    alerts = [a for a in build_alerts(d["results"] if d else []) if a.id not in false_alarms]
    print(notifier.status()[1])
    for a in alerts:
        who = notifier.recipients(a, con)
        tag = "URGENTE" if a.r.get("urgent") else "resumen"
        if args.dry_run:
            print(f"  {a.id} {tag:8} {short_supplier(a.supplier.name)}: {len(who)} chats")
            continue
        rep = notifier.notify(a, args.split, args.demo, con, background=False)
        print(f"  {a.id} {tag:8} {short_supplier(a.supplier.name)}: {rep.text()}")


if __name__ == "__main__":
    main()
