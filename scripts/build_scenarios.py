"""Interpreta con el LLM los escenarios de ejemplo del simulador y los guarda en data/scenarios.json.

    python scripts/build_scenarios.py

Así el simulador del panel funciona sin Ollama con estos ejemplos: lo único que hace el LLM es convertir
el texto en un escenario estructurado; el cálculo del impacto lo hace el código en el momento.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import scenario                                   # noqa: E402
from core.config import LLM_MODEL                           # noqa: E402


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=LLM_MODEL)
    args = ap.parse_args()
    from core import llm
    if not llm.is_up():
        sys.exit("Ollama no responde. Arráncalo (ollama serve).")
    items = []
    for text in scenario.EXAMPLES:
        sc, dropped = scenario.interpret(text, model=args.model)
        imp = scenario.simulate(sc)
        items.append({"text": text, "scenario": sc.model_dump(), "dropped": dropped})
        print(f"{text}\n   -> {sc.model_dump(exclude={'title'})}\n   -> {imp.supplier_ids}"
              + (f" · sin proveedores: {imp.unmatched_places}" if imp.unmatched_places else "")
              + (f" · descartado (no está en el texto): {dropped}" if dropped else ""))
    scenario.save_examples(items, args.model)
    print(f"Guardado: {scenario.EXAMPLES_PATH}")


if __name__ == "__main__":
    main()
