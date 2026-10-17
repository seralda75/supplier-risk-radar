"""Modo solo reglas (--no-llm): tipo de evento por palabras clave, gravedad y proveedores afectados.

Sirve de línea base medible y para probar sin GPU. Las palabras clave salen de las 30 noticias
de entrenamiento y de los ejemplos del README (incendio, regulador que para envíos, desastre
natural, veto a la exportación, proveedor al borde de la quiebra), más sinónimos generales.
También se reutiliza en el modo LLM: `select_ids` decide el ámbito de un evento de zona.
"""
from __future__ import annotations

import re

from .matching import Candidate, has_context_support, normalize
from .schemas import NewsAssessment

# ---------------------------------------------------------------------------
# Tipo de evento: se prueba en este orden y gana el primero que coincide
# (el veto a la exportación o la quiebra pesan más que cualquier otra palabra de la noticia;
#  "huracán ... cortes de luz" es un desastre natural, no un corte de suministro eléctrico)
# ---------------------------------------------------------------------------
EVENT_PATTERNS: list[tuple[str, list[str]]] = [
    ("export_restriction", [r"export (ban|bans|restriction|restrictions|licensing|licences?|licenses?|controls?|curbs?)",
                            r"ban(s|ned)? (on )?exports?", r"restrict\w* exports?"]),
    ("financial_distress", [r"going concern", r"bankrupt", r"insolven", r"chapter 11", r"liquidat",
                            r"default(ed|s)? on", r"missed (a |an |its )?(\w+ )?(bond|debt|loan|interest|coupon|payment)",
                            r"creditors", r"downgrad", r"rating agency", r"debt restructur", r"profit warning"]),
    ("cyber_incident", [r"ransomware", r"cyber ?attack", r"hack(ed|ers|ing)?", r"malware", r"data breach"]),
    ("quality_recall", [r"recall(s|ed|ing)?"]),
    ("natural_disaster", [r"flood(s|ed|ing)?", r"earthquake", r"quake", r"tremors?", r"hurricane", r"typhoon",
                          r"cyclone", r"tornado", r"tsunami", r"wildfires?", r"landslides?", r"monsoon",
                          r"storm", r"volcan", r"eruption", r"drought", r"blizzard", r"snowstorm"]),
    ("fire_plant_incident", [r"(?<!wild)fires?", r"blaze", r"explosion", r"exploded", r"blast",
                             r"(chemical|gas|toxic) leak", r"evacuat\w*", r"plant (incident|accident)"]),
    ("utility_outage", [r"power (outage|outages|cut|cuts|rationing|shortage|shortages)", r"blackouts?",
                        r"electricity (shortage|rationing|cuts?)", r"water (shortage|rationing)", r"load shedding"]),
    ("labour_strike", [r"strike", r"strikes", r"walkout", r"industrial action", r"work stoppage", r"lockout"]),
    ("regulatory_action", [r"warning letter", r"import alert", r"suspend\w*", r"revok\w*", r"consent decree",
                           r"licen[cs]e (suspended|revoked|withdrawn)", r"data integrity", r"shut down by",
                           r"non ?compliance"]),
    ("logistics_disruption", [r"reroute\w*", r"divert\w*", r"port (closure|closures|closed|congestion)",
                              r"congestion", r"blockades?", r"block(ed|ing|s)? (a |the )?(main )?(highway|road|roads|port|access)",
                              r"barges?", r"low water", r"water levels", r"delaying deliveries", r"slower deliveries",
                              r"containers? waiting"]),
    ("geopolitical_conflict", [r"sanctions?", r"embargo", r"war", r"military", r"armed conflict", r"tariffs?"]),
    ("supply_shortage", [r"shortages?", r"lead times?", r"backorders?", r"delay\w* shipments", r"ship \w+ late",
                         r"(reduce|cut)\w* (output|production)"]),
    ("acquisition", [r"acquir\w*", r"acquisition", r"takeover", r"merger", r"(agreed|agrees|agree) to buy",
                     r"to be bought"]),
    ("leadership_change", [r"(chief executive|ceo|cfo|chairman|chief operating officer|president) "
                           r"(has )?(steps|stepped|step) down", r"(resign|resigns|resigned|ousted|departs)",
                           r"steps down", r"stepped down"]),
    ("positive_news", [r"no observations", r"doubl\w*", r"expan\w*", r"capacity", r"contract", r"deal",
                       r"agreement", r"award\w*", r"approv\w*", r"financing", r"credit line", r"invest\w*",
                       r"opens", r"opened", r"record", r"certif\w*", r"partnership", r"wins"]),
]
_COMPILED = [(ev, [re.compile(r"(?<![a-z])" + p + r"(?![a-z])") for p in pats]) for ev, pats in EVENT_PATTERNS]

NON_RISK_EVENTS = {"positive_news", "not_relevant"}
# Eventos que no paran el suministro a corto plazo (README: "slow-moving effects")
SLOW_EVENTS = {"acquisition", "leadership_change"}
# Eventos de zona: afectan a todo lo que está en el área, no solo a la empresa nombrada
AREA_EVENTS = {"natural_disaster", "fire_plant_incident", "utility_outage", "labour_strike",
               "logistics_disruption", "export_restriction", "geopolitical_conflict"}
# Eventos que pueden afectar a todo un país aunque no se cite la ciudad
COUNTRY_WIDE_EVENTS = {"export_restriction", "labour_strike", "regulatory_action", "utility_outage",
                       "geopolitical_conflict", "natural_disaster"}
# Eventos que afectan a quien suministra un material aunque no se cite el lugar
MATERIAL_EVENTS = {"supply_shortage", "export_restriction", "quality_recall"}
# Eventos de transporte: afectan a bienes físicos, no a servicios (software, laboratorio)
TRANSPORT_EVENTS = {"labour_strike", "logistics_disruption"}

# Gravedad de partida por tipo de evento (1-5) y pistas del texto que la suben o la bajan
BASE_SEVERITY = {
    "fire_plant_incident": 4, "natural_disaster": 3, "export_restriction": 4, "financial_distress": 2,
    "cyber_incident": 3, "quality_recall": 4, "regulatory_action": 3, "utility_outage": 3, "labour_strike": 2,
    "geopolitical_conflict": 3, "logistics_disruption": 2, "supply_shortage": 3, "acquisition": 2,
    "leadership_change": 1, "other_risk": 2, "positive_news": 1, "not_relevant": 1,
}
# "proveedor al borde de la quiebra" es urgente según el README; una rebaja de rating no (N050)
DISTRESS_SEVERE = [r"going concern", r"bankrupt", r"insolven", r"chapter 11", r"liquidat", r"default(ed|s)? on",
                   r"missed (a |an |its )?(\w+ )?(bond|debt|loan|interest|coupon|payment)"]
UP_CUES = [r"halt\w*", r"shut\w*", r"closed", r"closures?", r"paused production", r"suspend\w*", r"stopped",
           r"evacuat\w*", r"destroy\w*", r"island ?wide", r"across the island", r"indefinite\w*",
           r"(several|three|two|four|many|\d+) (weeks|months)", r"(take|last) (weeks|months)", r"category [345]",
           r"power is out", r"offline"]
DOWN_CUES = [r"no injuries", r"minor", r"limited", r"only light", r"light shaking", r"safety checks",
             r"precaution\w*", r"temporar\w*", r"reduced loads", r"slower", r"partial\w*", r"resumed",
             r"no supply impact", r"\d+ hours", r"(24|48|72) hour"]


def _rx(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(r"(?<![a-z])" + p + r"(?![a-z])") for p in patterns]


_DISTRESS, _UP, _DOWN = _rx(DISTRESS_SEVERE), _rx(UP_CUES), _rx(DOWN_CUES)


def _any(patterns: list[re.Pattern], text: str) -> re.Match | None:
    return next((m for p in patterns if (m := p.search(text))), None)


def classify_event(headline: str, summary: str = "") -> tuple[str, str]:
    """Devuelve (event_type, palabra que lo ha disparado). El titular manda sobre el resumen."""
    for text in (normalize(headline), normalize(f"{headline}. {summary}")):
        for ev, pats in _COMPILED:
            if m := _any(pats, text):
                return ev, m.group(0)
    return "not_relevant", ""


def estimate_severity(event: str, headline: str, summary: str = "") -> int:
    text = normalize(f"{headline}. {summary}")
    sev = BASE_SEVERITY.get(event, 2)
    if event == "financial_distress" and _any(_DISTRESS, text):
        sev = 4
    if event not in NON_RISK_EVENTS:
        sev += (1 if _any(_UP, text) else 0) - (1 if _any(_DOWN, text) else 0)
    return max(1, min(5, sev))


def evidence_sentence(headline: str, summary: str, keyword: str) -> str:
    """La frase de la noticia que contiene la palabra clave (o el titular)."""
    if keyword:
        for sent in re.split(r"(?<=[.!?])\s+", f"{headline}. {summary}"):
            if keyword.split()[0] in normalize(sent):
                return sent.strip()
    return headline


# ---------------------------------------------------------------------------
# Selección de proveedores afectados
# ---------------------------------------------------------------------------

def verified_named(cands: list[Candidate], headline: str, summary: str = "") -> list[Candidate]:
    """Proveedores citados por su nombre. Un nombre parcial ('Celtic', 'Lumina') solo cuenta si
    algo más de la noticia apunta a ese proveedor (material, ciudad, vocabulario farmacéutico)."""
    return [c for c in cands if c.named or (c.ambiguous_name and has_context_support(c, headline, summary))]


def select_ids(cands: list[Candidate], event: str, headline: str, summary: str = "") -> list[str]:
    named = verified_named(cands, headline, summary)
    if event in NON_RISK_EVENTS:
        # noticia positiva o neutra: lleva el ID solo si nombra al proveedor (patrón del entrenamiento)
        return sorted(c.id for c in named)
    if named and event not in AREA_EVENTS:
        return sorted(c.id for c in named)

    located = [c for c in cands if c.specific_location]
    if not located and event in COUNTRY_WIDE_EVENTS:
        located = [c for c in cands if c.has("location", "country")]
    if event in MATERIAL_EVENTS:
        located += [c for c in cands if c.has("material") and c not in located]
    if event in TRANSPORT_EVENTS:
        located = [c for c in located if c.supplier.physical]
    # Si la noticia acota la categoría ("distribuidores químicos a lo largo del río"), se respeta
    by_cat = [c for c in located if c.has("category")]
    if len(located) > 1 and by_cat:
        located = by_cat
    ids = {c.id for c in located} | {c.id for c in named}
    return sorted(ids)


def assess_rules(headline: str, summary: str, cands: list[Candidate]) -> NewsAssessment:
    """Veredicto completo solo con reglas (mismo esquema que el juez LLM)."""
    event, keyword = classify_event(headline, summary)
    ids = select_ids(cands, event, headline, summary)
    is_risk = event not in NON_RISK_EVENTS and bool(ids)
    if event not in NON_RISK_EVENTS and not ids:
        event = "not_relevant"          # riesgo genérico sin relación con ningún proveedor
    severity = estimate_severity(event, headline, summary) if is_risk else 1
    return NewsAssessment(
        evidence=evidence_sentence(headline, summary, keyword),
        affected_ids=ids,
        event_type=event,
        is_risk=is_risk,
        severity=severity,
        stops_supply_soon=is_risk and severity >= 3 and event not in SLOW_EVENTS,
        recovery_days=None,
        confidence=0.6,
    )
