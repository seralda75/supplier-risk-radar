"""Genera los resultados que lee el panel (data/results/{split}.json).

    python scripts/build_results.py              # los tres conjuntos, con el juez LLM
    python scripts/build_results.py --no-llm     # solo reglas (sin GPU)
    python scripts/build_results.py --split test

Usa la caché del LLM: si ya se ejecutaron evaluate.py y fill_test.py, tarda segundos.
En entrenamiento cada noticia se evalúa sin verse a sí misma como ejemplo (leave-one-out),
igual que en evaluate.py. No escribe en la auditoría (eso lo hacen fill_test.py y el flujo real).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import results                                    # noqa: E402
from core.config import LLM_MODEL                           # noqa: E402
from core.data import load_news                             # noqa: E402
from core.pipeline import assess                            # noqa: E402


def build(split: str, use_llm: bool, model: str) -> int:
    out = []
    for n in load_news(split):
        kw = {"use_llm": use_llm, "log": False, "model": model}
        if use_llm and split == "train":
            kw["exclude_examples"] = {n["News_ID"]}
        r = assess(n, **kw).model_dump()
        r["summary"] = n.get("Summary", "")
        if "Is_Risk" in n:                       # etiquetas oficiales (no existen en el test)
            r["gold"] = {"is_risk": n["Is_Risk"] == "Y", "urgent": n["Urgent"] == "Y",
                         "affected_ids": sorted(n["Affected_Supplier_IDs"]),
                         "event_type": n.get("Event_Type", ""), "explanation": n.get("Explanation", "")}
        out.append(r)
    results.save(split, out, "llm" if use_llm else "reglas", model if use_llm else "")
    return len(out)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=list(results.SPLITS), nargs="*", default=list(results.SPLITS))
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--model", default=LLM_MODEL)
    args = ap.parse_args()
    use_llm = not args.no_llm
    if use_llm:
        from core import llm
        if not llm.is_up():
            sys.exit("Ollama no responde. Arráncalo (ollama serve) o usa --no-llm.")
    for split in args.split:
        n = build(split, use_llm, args.model)
        print(f"  {split}: {n} noticias -> {results.path(split)}")


if __name__ == "__main__":
    main()
