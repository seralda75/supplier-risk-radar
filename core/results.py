"""Resultados guardados del pipeline, para que el panel no llame al LLM al abrirse.

    python scripts/build_results.py          # genera data/results/{train,validation,test}.json

Cada fichero guarda el AssessmentResult completo de cada noticia (veredicto, cuenta atrás, consenso,
motivos de revisión...) y, en entrenamiento y validación, las etiquetas oficiales para medir.
"""
from __future__ import annotations

import json
from datetime import datetime

from .config import DATA_DIR

RESULTS_DIR = DATA_DIR / "results"
SPLITS = {"test": "Test (entrega)", "validation": "Validación", "train": "Entrenamiento"}


def path(split: str):
    return RESULTS_DIR / f"{split}.json"


def save(split: str, results: list[dict], mode: str, model: str) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"split": split, "generated": datetime.now().isoformat(timespec="seconds"),
               "mode": mode, "model": model, "results": results}
    path(split).write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def load(split: str) -> dict | None:
    p = path(split)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def rules_answer(r: dict) -> dict:
    """Respuesta del modo solo reglas para la misma noticia (guardada en signals en modo LLM)."""
    ra = r.get("signals", {}).get("rules_answer")
    if ra is None:                       # sin candidatos o modo reglas: la respuesta es la de las reglas
        return {"is_risk": r["is_risk"], "urgent": r["urgent"], "affected_ids": sorted(r["affected_ids"])}
    return ra


def metrics(results: list[dict], judge: str = "final") -> dict:
    """Métricas contra las etiquetas (solo entrenamiento y validación). judge: 'final' o 'reglas'."""
    rows = [r for r in results if r.get("gold")]
    if not rows:
        return {}
    ok_risk = ok_urg = ok_ids = perfect = tp = gold_u = pred_u = 0
    for r in rows:
        ans = rules_answer(r) if judge == "reglas" else r
        g = r["gold"]
        risk, urg, ids = ans["is_risk"], ans["urgent"], set(ans["affected_ids"])
        a = risk == g["is_risk"]
        b = urg == g["urgent"]
        c = ids == set(g["affected_ids"])
        ok_risk, ok_urg, ok_ids, perfect = ok_risk + a, ok_urg + b, ok_ids + c, perfect + (a and b and c)
        tp, gold_u, pred_u = tp + (urg and g["urgent"]), gold_u + g["urgent"], pred_u + urg
    n = len(rows)
    return {"Noticias": n, "Is_Risk": ok_risk / n, "Urgent": ok_urg / n,
            "Recall urgentes": tp / gold_u if gold_u else float("nan"),
            "Precisión urgentes": tp / pred_u if pred_u else float("nan"),
            "IDs exactos": ok_ids / n, "Noticia perfecta": perfect / n}


def is_perfect(r: dict) -> bool | None:
    g = r.get("gold")
    if not g:
        return None
    return (r["is_risk"] == g["is_risk"] and r["urgent"] == g["urgent"]
            and set(r["affected_ids"]) == set(g["affected_ids"]))
