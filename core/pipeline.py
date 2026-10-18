"""Orquestación: noticia -> candidatos -> veredicto -> urgencia -> explicación + acción -> auditoría.

    assess(news) -> AssessmentResult

`use_llm=False` (modo --no-llm) usa solo reglas: sirve de línea base y para probar sin GPU.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from . import audit
from .config import CONFIDENCE_THRESHOLD, LLM_MODEL
from .actions import recommend_action
from .countdown import as_dicts, countdown
from .matching import Candidate, find_candidates
from .rules import assess_rules, severity_signal, verified_named
from .schemas import EVENT_LABELS, EVENT_LABELS_ES, NewsAssessment
from .suppliers import Supplier, load_suppliers
from .urgency import combine_with_rules, dependency, is_urgent


class AssessmentResult(BaseModel):
    """Resultado completo de una noticia: lo que se entrega, lo que se explica y lo que se audita."""
    news_id: str
    headline: str
    published_date: str = ""
    source: str = ""
    is_risk: bool
    urgent: bool
    affected_ids: list[str]
    event_type: str
    event_label: str
    severity: int
    stops_supply_soon: bool
    recovery_days: int | None
    recovery_reported: str = ""                  # la duración tal como la da la noticia ("48 hours")
    evidence: str
    confidence: float
    urgency_reason: str
    explanation: str
    action: str
    needs_review: bool
    review_reasons: list[str] = Field(default_factory=list)   # "confianza_baja", "sin_consenso"
    mode: str                                   # "llm" o "reglas"
    model: str = ""
    examples: list[str] = Field(default_factory=list)   # noticias de entrenamiento usadas como ejemplo
    signals: dict = Field(default_factory=dict)          # gravedad según el LLM y según las reglas
    # ¿Coinciden las reglas y el LLM en las tres respuestas (Is_Risk, Urgent, IDs)? None en modo reglas.
    # Son dos jueces independientes: si discrepan, la decisión es menos segura.
    consensus: bool | None = None
    disagreement: list[str] = Field(default_factory=list)  # campos en los que discrepan
    dependencies: list[dict] = Field(default_factory=list)
    countdown: list[dict] = Field(default_factory=list)   # TTS, TTR y margen por proveedor (core/countdown.py)
    candidates: list[dict] = Field(default_factory=list)

    def to_row(self) -> dict:
        """Las tres columnas de la entrega, con el formato exacto."""
        return {"Is_Risk": "Y" if self.is_risk else "N",
                "Urgent": "Y" if self.urgent else "N",
                "Affected_Supplier_IDs": "; ".join(sorted(self.affected_ids))}


# ---------------------------------------------------------------------------
# Explicación (mismo esquema que la columna Explanation del reto); la acción está en actions.py
# ---------------------------------------------------------------------------

def _who(s: Supplier) -> str:
    return f"{s.id} {s.name}"


def explain(a: NewsAssessment, urgent: bool, cands: list[Candidate], headline: str, summary: str) -> str:
    sup = load_suppliers()
    by_id = {c.id: c for c in cands}
    label = EVENT_LABELS_ES.get(a.event_type, a.event_type)
    if a.is_risk:
        parts = []
        for i in a.affected_ids:
            c = by_id.get(i)
            how = "citado en la noticia" if c and c.named else "situado en la zona afectada"
            parts.append(f"{_who(sup[i])} ({how})")
        text = "Riesgo para " + ", ".join(parts) + ". "
        if urgent:
            return text + f"Urgente: este evento ({label}) puede parar o retrasar seriamente el suministro pronto."
        return text + (f"No urgente: {label} con impacto limitado o de corta duración; "
                       "puede esperar al informe semanal.")
    if a.event_type == "positive_news" and a.affected_ids:
        return "Sin riesgo: noticia positiva sobre " + ", ".join(_who(sup[i]) for i in a.affected_ids) + "."
    if a.affected_ids:
        return "Sin riesgo: noticia sobre " + ", ".join(_who(sup[i]) for i in a.affected_ids) + \
               " que no afecta al suministro."
    named = {c.id for c in verified_named(cands, headline, summary)}
    lookalike = next((c for c in cands if c.ambiguous_name and c.id not in named), None)
    if lookalike:
        return (f"Sin riesgo: el nombre se parece a {_who(lookalike.supplier)}, pero la noticia trata de "
                "otra organización o tema.")
    place = next((c for c in cands if c.has("location", "city", "region")), None)
    if place:
        alias = next(r.alias for r in place.reasons if r.kind == "location")
        return (f"Sin riesgo: menciona {alias}, donde está {_who(place.supplier)}, pero no describe nada "
                "que afecte al suministro.")
    return "Sin riesgo: sin relación con ningún proveedor de Helixa."


# ---------------------------------------------------------------------------
# Desempate cuando las reglas y el LLM discrepan
# ---------------------------------------------------------------------------

# Quién decide cada campo si los dos jueces no coinciden ("llm" o "reglas"). Decidido con el
# entrenamiento (leave-one-out) y la validación, nunca con el test: en 40 noticias solo hay 4
# discrepancias y ningún juez gana con claridad, así que manda el LLM (docs/evaluacion.md, v5).
# El cliente puede cambiarlo cuando tenga más histórico (por ejemplo, con la respuesta de los compradores).
TIEBREAK = {"Is_Risk": "llm", "Urgent": "llm", "Affected_Supplier_IDs": "llm"}


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def assess(news: dict, use_llm: bool = True, log: bool = True, model: str = LLM_MODEL,
           exclude_examples: set[str] | None = None) -> AssessmentResult:
    """Evalúa una noticia (dict con News_ID, Headline, Summary...).

    use_llm=False -> solo reglas. Sin candidatos no se llama al LLM: no hay ningún proveedor
    relacionado, así que la respuesta es 'sin riesgo' sin gastar ~20 s de GPU.
    exclude_examples -> IDs que no pueden usarse como ejemplo (leave-one-out en entrenamiento).
    """
    headline, summary = news["Headline"], news.get("Summary", "") or ""
    cands = find_candidates(headline, summary)
    examples: list[str] = []
    signals: dict = {}
    mode = "llm" if use_llm and cands else "reglas"
    if mode == "llm":
        from .judge import judge
        a, examples, raw = judge(headline, summary, cands, model=model, exclude_ids=exclude_examples)
        rules_sev, rules_soon = severity_signal(headline, summary)
        signals = {"severity_llm": a.severity, "soon_llm": a.stops_supply_soon,
                   "severity_rules": rules_sev, "soon_rules": rules_soon}
        if raw.recovery_value is not None:
            # Duración que dio el LLM y si está escrita en la noticia (judge.duration_in_text)
            signals["recovery_llm"] = f"{raw.recovery_value:g} {raw.recovery_unit or 'days'}"
            signals["recovery_anchored"] = a.recovery_value is not None
        a = combine_with_rules(a, rules_sev, rules_soon)
        rules_a = assess_rules(headline, summary, cands)
    else:
        a, model = assess_rules(headline, summary, cands), ""

    sup = load_suppliers()
    deps = [dependency(sup[i]) for i in a.affected_ids]
    urgent, why = is_urgent(a, deps)
    consensus, disagreement = None, []
    if mode == "llm":
        rules_urgent, rules_why = is_urgent(rules_a, [dependency(sup[i]) for i in rules_a.affected_ids])
        disagreement = [field for field, llm_v, rules_v in (
            ("Is_Risk", a.is_risk, rules_a.is_risk), ("Urgent", urgent, rules_urgent),
            ("Affected_Supplier_IDs", sorted(a.affected_ids), sorted(rules_a.affected_ids))) if llm_v != rules_v]
        consensus = not disagreement
        signals["rules_answer"] = {"is_risk": rules_a.is_risk, "urgent": rules_urgent,
                                   "affected_ids": sorted(rules_a.affected_ids)}
        # Desempate campo a campo según TIEBREAK (con la política actual, el LLM en todos)
        winners = {f: TIEBREAK[f] for f in disagreement}
        signals["tiebreak"] = winners
        if winners.get("Is_Risk") == "reglas":
            a = a.model_copy(update={"is_risk": rules_a.is_risk})
        if winners.get("Affected_Supplier_IDs") == "reglas":
            a = a.model_copy(update={"affected_ids": rules_a.affected_ids})
        if winners.get("Urgent") == "reglas":
            urgent, why = rules_urgent, rules_why
        if not a.is_risk:
            urgent, why = False, "no es un riesgo"            # solo un riesgo puede ser urgente
        deps = [dependency(sup[i]) for i in a.affected_ids]
    elif use_llm:
        consensus = True     # sin candidatos el LLM no puede dar otra respuesta: sin riesgo y sin IDs
    # Revisión humana: la confianza declarada por el LLM es casi constante y no separa aciertos de
    # errores (docs/evaluacion.md, v7); la discrepancia entre los dos jueces sí. Se guardan los motivos.
    review_reasons = []
    if a.is_risk and a.confidence < CONFIDENCE_THRESHOLD:
        review_reasons.append("confianza_baja")
    if consensus is False:
        review_reasons.append("sin_consenso")
    needs_review = bool(review_reasons)
    cds = countdown(a, urgent)       # la acción recomendada se calcula a partir de la cuenta atrás
    result = AssessmentResult(
        news_id=news["News_ID"], headline=headline, published_date=str(news.get("Published_Date", "")),
        source=news.get("Source", "") or "", is_risk=a.is_risk, urgent=urgent, affected_ids=sorted(a.affected_ids),
        event_type=a.event_type, event_label=EVENT_LABELS.get(a.event_type, a.event_type), severity=a.severity,
        stops_supply_soon=a.stops_supply_soon, recovery_days=a.recovery_days,
        recovery_reported="" if a.recovery_value is None else f"{a.recovery_value:g} {a.recovery_unit or 'days'}",
        evidence=a.evidence,
        confidence=a.confidence, urgency_reason=why, explanation=explain(a, urgent, cands, headline, summary),
        action=recommend_action(a, urgent, cds), needs_review=needs_review, review_reasons=review_reasons, mode=mode,
        model=model, examples=examples, signals=signals, consensus=consensus, disagreement=disagreement,
        dependencies=[d.__dict__ for d in deps],
        countdown=as_dicts(cds),
        candidates=[{"id": c.id, "name": c.supplier.name, "score": c.score, "evidence": c.evidence()}
                    for c in cands],
    )
    if log:
        audit.log(result)
    return result
