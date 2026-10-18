"""Juez LLM: confirma o descarta candidatos (nombres trampa), clasifica el evento y su gravedad.

    judge(headline, summary, candidates) -> NewsAssessment

- Few-shot dinámico: las noticias de ENTRENAMIENTO más parecidas (Chroma + nomic-embed-text), con
  su etiqueta y su Explanation, que es el razonamiento que el README pide copiar.
- Salida estructurada: JSON schema de NewsAssessment en `format` de Ollama + validación Pydantic.
- Salvaguardas deterministas después del LLM: no puede inventar IDs, un nombre ambiguo necesita
  contexto que lo respalde, una noticia sin riesgo solo lleva IDs de proveedores citados por su
  nombre, y un evento de transporte no afecta a servicios.
"""
from __future__ import annotations

from . import llm, rag
from .config import LLM_MODEL
from .data import format_ids, load_news
from .matching import Candidate, has_context_support
from .rules import TRANSPORT_EVENTS
from .schemas import NewsAssessment

COLLECTION = "train_news"     # Chroma exige nombres de al menos 3 caracteres
N_EXAMPLES = 4

SYSTEM = """You are a supply-risk analyst for Helixa Pharmaceuticals, a drug maker that depends on the \
suppliers listed as CANDIDATES. For ONE news article you must decide:

1. Identity. A candidate whose name only partly matches (marked AMBIGUOUS NAME) may be a different \
organisation, a film, a sports team or another company with a similar name. Only keep it if the article \
is really about that supplier.
2. Location. A supplier that is not named still counts if it is located in the affected area (city, \
region, river, port) or depends on the affected route, AND the event can physically affect it there. \
A place that is merely mentioned (a conference, an airport record, a currency move) is NOT a risk.
3. Category. Transport disruptions (strikes of truckers or port workers, blocked roads, ports, low water \
on rivers, rerouted sea routes) affect suppliers of physical goods and logistics providers located there, \
not software or service providers. They are risks even when the impact is only slower deliveries.
4. is_risk is true if the event can stop, reduce or delay supply from at least one candidate, or weakens \
a supplier: acquisition by a competitor, leadership change, credit downgrade or financial trouble at a \
named supplier ARE risks (usually low severity, not urgent).
5. Positive or neutral news about a NAMED supplier: is_risk = false, but still list its ID. If is_risk is \
false and the supplier is not named, affected_ids must be empty.
6. severity (1-5) of the event for the affected supplier:
   1 = no impact on supply.
   2 = minor, slow-moving or easy to absorb: ownership change, leadership change, credit rating downgrade, \
price increase, short strike or protest, port congestion, longer transit times, partial or reduced output.
   3 = real but limited disruption: production or deliveries affected for days to a couple of weeks, \
stock losses, precautionary closures, partial restrictions.
   4 = serious: a plant stopped or closed, a regulator stopping production or shipments, a natural \
disaster closing factories, an export ban, a supplier close to bankruptcy, a product recall.
   5 = catastrophic: long shutdown (months) or the supplier may disappear.
7. stops_supply_soon = true only if the event itself can stop or seriously delay deliveries within days \
or weeks. False for slow-moving effects (ownership or leadership change, credit downgrade, price changes).
8. recovery_days: days until the supplier is back to normal according to the article ("three weeks" -> 21, \
"two months" -> 60, "48 hours" -> 2); null if the article gives no basis to estimate it.
9. evidence: copy the sentence of the article that supports your decision.
10. Use only IDs from the CANDIDATES list. Follow the style of the labelled examples.
11. confidence: a decimal from 0.0 to 1.0 with how sure you are that your own answer is correct. It is not the probability of a risk and not a 1-5 score.
Answer with JSON only."""


# ---------------------------------------------------------------------------
# Ejemplos del entrenamiento (Chroma)
# ---------------------------------------------------------------------------

def _example_text(n: dict) -> str:
    return f"{n['Headline']}. {n['Summary']}"


def ensure_index() -> int:
    """Indexa las 30 noticias de entrenamiento (solo si faltan). Nunca indexa validación ni test."""
    train = load_news("train")
    if rag.count(COLLECTION) == len(train):
        return len(train)
    rag.reset(COLLECTION)
    return rag.index_records([{
        "id": n["News_ID"], "text": _example_text(n), "headline": n["Headline"], "summary": n["Summary"],
        "is_risk": n["Is_Risk"], "urgent": n["Urgent"], "ids": format_ids(n["Affected_Supplier_IDs"]),
        "event_type": n["Event_Type"], "explanation": n["Explanation"],
    } for n in train], COLLECTION)


def similar_examples(headline: str, summary: str, k: int = N_EXAMPLES,
                     exclude_ids: set[str] | None = None) -> list[dict]:
    ensure_index()
    return rag.search(f"{headline}. {summary}", COLLECTION, k=k, exclude_ids=exclude_ids)


def _format_example(e: dict) -> str:
    return (f"Headline: {e['headline']}\nSummary: {e['summary']}\n"
            f"Label: Is_Risk={e['is_risk']}, Urgent={e['urgent']}, Affected_Supplier_IDs=[{e['ids']}], "
            f"Event_Type={e['event_type']}\nWhy: {e['explanation']}")


def _format_candidate(c: Candidate) -> str:
    flag = " | AMBIGUOUS NAME: verify identity" if c.ambiguous_name else ""
    return f"- {c.supplier.card()}\n  matched by: {c.evidence()}{flag}"


def build_prompt(headline: str, summary: str, cands: list[Candidate],
                 exclude_ids: set[str] | None = None) -> tuple[str, list[str]]:
    examples = similar_examples(headline, summary, exclude_ids=exclude_ids)
    prompt = (
        "LABELLED EXAMPLES (similar past articles):\n\n"
        + "\n\n".join(_format_example(e) for e in examples)
        + "\n\nCANDIDATES (Helixa suppliers that may be involved):\n"
        + "\n".join(_format_candidate(c) for c in cands)
        + f"\n\nARTICLE TO ASSESS:\nHeadline: {headline}\nSummary: {summary}"
    )
    return prompt, [e["id"] for e in examples]


# ---------------------------------------------------------------------------
# Juez
# ---------------------------------------------------------------------------

def apply_guards(a: NewsAssessment, cands: list[Candidate], headline: str = "",
                 summary: str = "") -> NewsAssessment:
    """Reglas de negocio que el LLM no puede saltarse."""
    by_id = {c.id: c for c in cands}
    ids = [i for i in a.affected_ids if i in by_id]                       # no se inventan IDs
    # Identidad: un nombre ambiguo (parcial) solo cuenta si algo más de la noticia apunta a ese
    # proveedor (material, ciudad, vocabulario farmacéutico). Es la misma comprobación del modo reglas.
    # Cambio motivado por un error de validación (ver docs/evaluacion.md, fase 2 v3).
    ids = [i for i in ids if not (by_id[i].ambiguous_name and not by_id[i].named
                                  and not has_context_support(by_id[i], headline, summary))]
    if a.event_type in TRANSPORT_EVENTS:                                  # el transporte no afecta al software
        ids = [i for i in ids if by_id[i].supplier.physical or by_id[i].named]
    is_risk = a.is_risk and bool(ids) and a.event_type not in {"positive_news", "not_relevant"}
    if not is_risk:
        # sin riesgo: solo se listan proveedores citados por su nombre (noticia positiva o neutra).
        # Un proveedor con su nombre completo en la noticia se lista siempre (patrón del entrenamiento:
        # "Sunrise BioChem completes US inspection" -> Is_Risk = N, IDs = S001)
        ids = sorted({i for i in ids if by_id[i].named or by_id[i].ambiguous_name}
                     | {c.id for c in cands if c.named})
    return a.model_copy(update={
        "affected_ids": sorted(ids), "is_risk": is_risk,
        "stops_supply_soon": a.stops_supply_soon and is_risk,
        "severity": a.severity if is_risk else 1,
    })


def judge(headline: str, summary: str, cands: list[Candidate], model: str = LLM_MODEL,
          exclude_ids: set[str] | None = None) -> tuple[NewsAssessment, list[str]]:
    """Devuelve el veredicto del LLM (ya con salvaguardas) y los IDs de los ejemplos usados."""
    prompt, used = build_prompt(headline, summary, cands, exclude_ids)
    raw = llm.extract(prompt, NewsAssessment, model=model, system=SYSTEM)
    return apply_guards(raw, cands, headline, summary), used
