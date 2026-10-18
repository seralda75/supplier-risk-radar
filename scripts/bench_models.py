"""Fase 0: compara modelos locales para el juez (latencia, validez del JSON y acierto orientativo).

Usa SOLO noticias de entrenamiento. El prompt imita al del juez final (fichas de los
candidatos + 3 ejemplos con su Explanation), para que la latencia medida sea realista.
Llama a Ollama sin caché ni reintentos: se mide si el JSON es válido al primer intento.

Uso:  python scripts/bench_models.py [modelo1 modelo2 ...]
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.config import NUM_CTX, OLLAMA_URL, TRAIN_XLSX  # noqa: E402
from core.schemas import NewsAssessment  # noqa: E402

MODELS = sys.argv[1:] or ["qwen2.5:7b", "qwen2.5:3b", "llama3.2:3b"]

# Noticias de entrenamiento a probar -> candidatos (los afectados + parecidos que el juez debe descartar)
BENCH = {
    "N001": ["S003", "S024"],          # incendio, proveedor único -> urgente
    "N007": ["S004"],                  # trampa: Orion Capital
    "N011": ["S013", "S027"],          # terremoto sur de Taiwán -> S013 sí, Hsinchu no
    "N017": ["S015"],                  # trampa: película 'Lumina'
    "N029": ["S025"],                  # huracán Puerto Rico -> urgente
    "N033": ["S001"],                  # noticia positiva: lleva el ID con is_risk = false
    "N046": ["S011", "S018", "S035"],  # huelga de camioneros: S035 es software
    "N050": ["S011"],                  # rebaja de rating -> riesgo no urgente
}
FEW_SHOT = ["N020", "N030", "N037"]

SYSTEM = (
    "You are a supply-risk analyst for Helixa Pharmaceuticals. Read one news article and decide: "
    "is it a risk to supply, which of the CANDIDATE suppliers it really refers to (verify identity: a "
    "similar name may be a different company, film or sports team), the event type, its severity and "
    "whether it can stop or seriously delay supply soon. Positive news about a supplier is not a risk "
    "but still lists that supplier. Only use IDs from the candidate list. Answer with JSON only."
)


def supplier_card(s: pd.Series) -> str:
    inv = "n/a" if pd.isna(s.Inventory_Cover_Days) else int(s.Inventory_Cover_Days)
    alt = s.Approved_Alternate_ID if isinstance(s.Approved_Alternate_ID, str) else "none"
    return (f"- {s.Supplier_ID} {s.Supplier_Name} | {s.Category}: {s.Material_Supplied} | "
            f"{s.City}, {s.Country} | single source: {s.Single_Source} | alternate: {alt} | "
            f"criticality: {s.Criticality} | inventory cover days: {inv}")


def example_block(n: pd.Series) -> str:
    return (f"Headline: {n.Headline}\nSummary: {n.Summary}\n"
            f"Answer: Is_Risk={n.Is_Risk}, Urgent={n.Urgent}, "
            f"IDs={n.Affected_Supplier_IDs if isinstance(n.Affected_Supplier_IDs, str) else ''}, "
            f"Event_Type={n.Event_Type}\nWhy: {n.Explanation}")


def build_prompt(n: pd.Series, cands: list[str], sup: pd.DataFrame, news: pd.DataFrame) -> str:
    cards = "\n".join(supplier_card(sup.loc[c]) for c in cands)
    shots = "\n\n".join(example_block(news.loc[i]) for i in FEW_SHOT)
    return (f"SIMILAR LABELLED EXAMPLES:\n{shots}\n\nCANDIDATE SUPPLIERS:\n{cards}\n\n"
            f"ARTICLE TO ASSESS:\nHeadline: {n.Headline}\nSummary: {n.Summary}")


def call(model: str, prompt: str) -> dict:
    t0 = time.perf_counter()
    r = requests.post(f"{OLLAMA_URL}/api/chat", timeout=600, json={
        "model": model, "stream": False, "format": NewsAssessment.model_json_schema(),
        "options": {"temperature": 0, "num_ctx": NUM_CTX},
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]})
    r.raise_for_status()
    body = r.json()
    body["wall_s"] = time.perf_counter() - t0
    return body


def vram_share(model: str) -> str:
    for m in requests.get(f"{OLLAMA_URL}/api/ps", timeout=5).json().get("models", []):
        if m["name"] == model:
            return f"{100 * m.get('size_vram', 0) / max(m['size'], 1):.0f}% GPU"
    return "?"


def main() -> None:
    sup = pd.read_excel(TRAIN_XLSX, sheet_name="Suppliers").set_index("Supplier_ID", drop=False)
    news = pd.read_excel(TRAIN_XLSX, sheet_name="News").set_index("News_ID", drop=False)
    rows = []
    for model in MODELS:
        print(f"\n=== {model}")
        for nid, cands in BENCH.items():
            n = news.loc[nid]
            prompt = build_prompt(n, cands, sup, news)
            body = call(model, prompt)
            gold_ids = set(str(n.Affected_Supplier_IDs).split("; ")) if isinstance(n.Affected_Supplier_IDs, str) else set()
            try:
                a = NewsAssessment.model_validate(json.loads(body["message"]["content"]))
                valid, risk_ok = True, a.is_risk == (n.Is_Risk == "Y")
                ids_ok = set(a.affected_ids) == gold_ids
                urg_ok = (a.is_risk and a.stops_supply_soon) == (n.Urgent == "Y")
                detail = f"risk={a.is_risk} ids={a.affected_ids} soon={a.stops_supply_soon} sev={a.severity} rec={a.recovery_value} {a.recovery_unit} {a.event_type}"
            except (json.JSONDecodeError, ValidationError) as e:
                valid = risk_ok = ids_ok = urg_ok = False
                detail = f"JSON NO VÁLIDO: {str(e)[:120]}"
            rows.append({"model": model, "news": nid, "valid": valid, "risk_ok": risk_ok, "ids_ok": ids_ok,
                         "urg_ok": urg_ok, "wall_s": body["wall_s"], "load_s": body.get("load_duration", 0) / 1e9,
                         "prompt_tok": body.get("prompt_eval_count", 0),
                         "gen_tok_s": body.get("eval_count", 0) / max(body.get("eval_duration", 1) / 1e9, 1e-9)})
            print(f"  {nid} {body['wall_s']:5.1f}s  {detail}")
        print(f"  ocupación: {vram_share(model)}")
        rows[-1]["vram"] = vram_share(model)

    df = pd.DataFrame(rows)
    # La primera llamada de cada modelo incluye la carga en memoria: se excluye de la latencia
    warm = df.groupby("model").apply(lambda g: g.iloc[1:], include_groups=False).reset_index(level=0)
    summary = pd.DataFrame({
        "carga_s": df.groupby("model")["load_s"].max().round(1),
        "lat_media_s": warm.groupby("model")["wall_s"].mean().round(1),
        "lat_max_s": warm.groupby("model")["wall_s"].max().round(1),
        "tok/s": warm.groupby("model")["gen_tok_s"].apply(statistics.median).round(1),
        "prompt_tok": df.groupby("model")["prompt_tok"].mean().round(0),
        "json_valido": df.groupby("model")["valid"].mean().map("{:.0%}".format),
        "is_risk": df.groupby("model")["risk_ok"].sum().astype(str) + f"/{len(BENCH)}",
        "ids": df.groupby("model")["ids_ok"].sum().astype(str) + f"/{len(BENCH)}",
        "urgente": df.groupby("model")["urg_ok"].sum().astype(str) + f"/{len(BENCH)}",
        "memoria": df.groupby("model")["vram"].last(),
    }).reindex(MODELS)
    print("\n" + summary.to_string())


if __name__ == "__main__":
    main()
