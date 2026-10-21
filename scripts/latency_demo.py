"""Latencia del modo demo y del agente de comunicaciones (sin navegador).

    python scripts/latency_demo.py                 # 5 noticias del guion y 5 alertas de test
    python scripts/latency_demo.py --n 10

Mide el pipeline real (assess) en directo (sin la caché del LLM) y con caché, y la redacción de las
comunicaciones en directo y con caché. Indica si el portátil está enchufado: en batería la GPU va más lenta.
En el panel hay que sumar las pausas de la demo (4 pasos × DEMO_STEP_S + DEMO_END_S ≈ 8,4 s).
No escribe en ninguna base de datos (assess con log=False).
"""
from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import comms, demo, llm, results               # noqa: E402
from core.data import load_news                          # noqa: E402
from core.pipeline import assess                         # noqa: E402


def power() -> str:
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "Add-Type -AssemblyName System.Windows.Forms; "
                              "[System.Windows.Forms.SystemInformation]::PowerStatus.PowerLineStatus"],
                             capture_output=True, text=True, timeout=20).stdout.strip()
        return {"Online": "enchufado", "Offline": "EN BATERÍA"}.get(out, out or "desconocido")
    except Exception:
        return "desconocido"


def timed(fn) -> tuple[float, object]:
    t = time.perf_counter()
    r = fn()
    return time.perf_counter() - t, r


def summary(name: str, xs: list[float]) -> None:
    if xs:
        print(f"  {name:<34} mediana {statistics.median(xs):5.1f} s · mín {min(xs):5.1f} · máx {max(xs):5.1f} "
              f"(n={len(xs)})")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=5)
    args = ap.parse_args()
    print(f"Corriente: {power()} · Ollama: {'sí' if llm.is_up() else 'NO'}")
    if not llm.is_up():
        sys.exit("Arranca Ollama (ollama serve) para medir.")
    llm.chat("OK", temperature=0)                        # calentar: el modelo ya en la GPU, como en la demo
    news = {n["News_ID"]: n for n in load_news("validation")}
    live, cached = [], []
    for nid in demo.FEED[:args.n]:
        t1, r = timed(lambda: assess(news[nid], log=False, use_cache=False))
        t2, _ = timed(lambda: assess(news[nid], log=False, use_cache=True))
        (live if r.mode == "llm" else []).append(t1)
        cached.append(t2)
        print(f"  {nid} {r.mode:<6} en directo {t1:5.1f} s · con caché {t2:4.1f} s · "
              f"{'riesgo' if r.is_risk else 'sin riesgo'}{' urgente' if r.urgent else ''}")
    from ui.comms_view import facts
    from ui.data import build_alerts
    alerts = build_alerts(results.load("test")["results"])[:args.n]
    c_live, c_cached = [], []
    for a in alerts:
        f = facts(a)
        t1, p = timed(lambda: comms.prepare(f, fresh=True))
        comms.prepare(f)                                 # deja la respuesta en la caché (si no estaba)
        t2, _ = timed(lambda: comms.prepare(f))
        c_live.append(t1)
        c_cached.append(t2)
        print(f"  {a.id} comunicaciones en directo {t1:5.1f} s ({p.source}, intentos {p.attempts}) · "
              f"con caché {t2:4.1f} s")
    print(f"\nResumen ({power()}):")
    summary("Pipeline, IA en directo", live)
    summary("Pipeline, IA con caché", cached)
    summary("Comunicaciones, IA en directo", c_live)
    summary("Comunicaciones, IA con caché", c_cached)


if __name__ == "__main__":
    main()
