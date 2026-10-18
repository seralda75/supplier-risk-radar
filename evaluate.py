"""Métricas del sistema sobre noticias etiquetadas.

    python evaluate.py                     # validación, con el juez LLM
    python evaluate.py --no-llm            # validación, solo reglas (línea base, sin GPU)
    python evaluate.py --split train       # entrenamiento (con LLM: ejemplos leave-one-out)

La validación SOLO se usa para medir: no se indexa en Chroma ni aparece en ningún prompt.
Prioridad: recall de las urgentes (no detectar un incendio es peor que una falsa alarma).
"""
from __future__ import annotations

import argparse
import sys
import time

import pandas as pd

from core.config import LLM_MODEL, OUTPUT_DIR
from core.data import load_news
from core.matching import find_candidates
from core.pipeline import assess
from core.schemas import EVENT_LABELS


def jaccard(a: set, b: set) -> float:
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def evaluate(split: str, use_llm: bool, model: str = LLM_MODEL, verbose: bool = True) -> tuple[dict, pd.DataFrame]:
    news = load_news(split)
    label_to_event = {v.lower(): k for k, v in EVENT_LABELS.items()}
    rows = []
    t0 = time.perf_counter()
    for n in news:
        kwargs = {"use_llm": use_llm, "log": False}
        if use_llm:
            kwargs["model"] = model
            if split == "train":
                kwargs["exclude_examples"] = {n["News_ID"]}   # leave-one-out: no verse a sí misma
        r = assess(n, **kwargs)
        gold_ids, pred_ids = set(n["Affected_Supplier_IDs"]), set(r.affected_ids)
        cand_ids = {c.id for c in find_candidates(n["Headline"], n["Summary"])}
        rows.append({
            "News_ID": n["News_ID"], "Headline": n["Headline"][:70],
            "gold_risk": n["Is_Risk"], "pred_risk": "Y" if r.is_risk else "N",
            "gold_urgent": n["Urgent"], "pred_urgent": "Y" if r.urgent else "N",
            "gold_ids": "; ".join(sorted(gold_ids)), "pred_ids": "; ".join(sorted(pred_ids)),
            "jaccard": jaccard(gold_ids, pred_ids), "ids_exact": gold_ids == pred_ids,
            "cand_recall_ok": gold_ids <= cand_ids,
            "gold_event": label_to_event.get(str(n["Event_Type"]).lower(), n["Event_Type"]),
            "pred_event": r.event_type, "severity": r.severity, "soon": r.stops_supply_soon,
            "recovery_days": r.recovery_days, "urgency_reason": r.urgency_reason,
            "consensus": r.consensus, "disagreement": ", ".join(r.disagreement),
        })
        if verbose:
            mark = "✔" if (rows[-1]["gold_risk"] == rows[-1]["pred_risk"] and rows[-1]["ids_exact"]
                           and rows[-1]["gold_urgent"] == rows[-1]["pred_urgent"]) else "✘"
            print(f"  {mark} {n['News_ID']} risk={rows[-1]['pred_risk']} urg={rows[-1]['pred_urgent']} "
                  f"ids=[{rows[-1]['pred_ids']}] {r.event_type} sev={r.severity}", flush=True)
    df = pd.DataFrame(rows)

    gold_u, pred_u = df.gold_urgent == "Y", df.pred_urgent == "Y"
    metrics = {
        "noticias": len(df),
        "acierto Is_Risk": (df.gold_risk == df.pred_risk).mean(),
        "acierto Urgent": (df.gold_urgent == df.pred_urgent).mean(),
        "recall urgentes": (gold_u & pred_u).sum() / max(gold_u.sum(), 1),
        "precisión urgentes": (gold_u & pred_u).sum() / max(pred_u.sum(), 1),
        "IDs exactos": df.ids_exact.mean(),
        "IDs Jaccard medio": df.jaccard.mean(),
        "noticia perfecta (3 campos)": ((df.gold_risk == df.pred_risk) & (df.gold_urgent == df.pred_urgent)
                                        & df.ids_exact).mean(),
        "recall de candidatos": df.cand_recall_ok.mean(),
        "acierto Event_Type": (df.gold_event == df.pred_event).mean(),
        "segundos por noticia": (time.perf_counter() - t0) / max(len(df), 1),
    }
    if use_llm:
        # ¿Sirve el consenso como señal de confianza? Acierto cuando reglas y LLM coinciden y cuando no
        perfect = ((df.gold_risk == df.pred_risk) & (df.gold_urgent == df.pred_urgent) & df.ids_exact)
        agree = df.consensus.astype(bool)
        metrics["consenso reglas-LLM"] = agree.mean()
        metrics["perfecta si hay consenso"] = perfect[agree].mean() if agree.any() else float("nan")
        metrics["perfecta si discrepan"] = perfect[~agree].mean() if (~agree).any() else float("nan")
    return metrics, df


def print_report(metrics: dict, df: pd.DataFrame, title: str) -> None:
    print(f"\n=== {title}")
    for k, v in metrics.items():
        if k == "noticias":
            print(f"  {k:<30} {v}")
        elif k == "segundos por noticia":
            print(f"  {k:<30} {v:.1f}")
        else:
            print(f"  {k:<30} {v:6.1%}")
    errors = df[(df.gold_risk != df.pred_risk) | (df.gold_urgent != df.pred_urgent) | ~df.ids_exact]
    if len(errors):
        print(f"\n  Errores ({len(errors)}):")
        cols = ["News_ID", "Headline", "gold_risk", "pred_risk", "gold_urgent", "pred_urgent", "gold_ids",
                "pred_ids", "pred_event", "severity", "soon", "consensus"]
        print(errors[cols].to_string(index=False))


def main() -> None:
    # La consola de Windows (o una tubería) usa cp1252 por defecto y no sabe imprimir ✔/✘/✅
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", choices=["validation", "train"], default="validation")
    ap.add_argument("--no-llm", action="store_true", help="solo reglas (sin Ollama)")
    ap.add_argument("--model", default=LLM_MODEL)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    use_llm = not args.no_llm
    if use_llm:
        from core import llm
        if not llm.is_up():
            sys.exit("Ollama no responde. Arráncalo (ollama serve) o usa --no-llm.")
    mode = f"LLM {args.model}" if use_llm else "solo reglas"
    metrics, df = evaluate(args.split, use_llm, args.model, verbose=not args.quiet)
    print_report(metrics, df, f"{args.split} · {mode}")
    out = OUTPUT_DIR / f"eval_{args.split}_{'llm_' + args.model.replace(':', '-') if use_llm else 'reglas'}.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n  Detalle guardado en {out}")


if __name__ == "__main__":
    main()
