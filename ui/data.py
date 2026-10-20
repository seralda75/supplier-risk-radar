"""Datos de las vistas de negocio, a partir de los resultados guardados (data/results/*.json).

Una alerta es una noticia de riesgo. Su nivel:
- "critica": Urgent = Y (gravedad × dependencia, la respuesta que se entrega).
- "vigilar": no urgente, pero algún proveedor tiene el margen negativo (riesgo latente).
- "seguimiento": el resto de riesgos (informe semanal).
La cola «Requiere tu decisión» son las críticas y las de vigilar, por días de margen.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime

from core.actions import situation
from core.countdown import MARGIN_TIGHT_DAYS, Countdown
from core.judge import NUMBER_WORDS, UNIT_STEMS
from core.labels import place_es, short_supplier
from core.suppliers import Supplier, load_suppliers

LEVEL_ORDER = {"critica": 0, "vigilar": 1, "seguimiento": 2}
UNIT_ES = {"hours": ("hora", "horas"), "days": ("día", "días"), "weeks": ("semana", "semanas"),
           "months": ("mes", "meses")}

# «Qué pasa», en una frase y sin jerga
EVENT_WHAT = {
    "fire_plant_incident": "Un incendio o incidente ha parado instalaciones del proveedor.",
    "natural_disaster": "Un desastre natural afecta a la zona donde está el proveedor.",
    "labour_strike": "Una huelga afecta a la producción o al transporte del proveedor.",
    "logistics_disruption": "Una interrupción logística retrasa los envíos del proveedor.",
    "regulatory_action": "Un regulador actúa contra el proveedor y puede bloquear sus envíos.",
    "quality_recall": "El proveedor retira lotes por un problema de calidad.",
    "export_restriction": "Una restricción a la exportación puede cortar los envíos del proveedor.",
    "financial_distress": "El proveedor atraviesa dificultades financieras.",
    "acquisition": "Un competidor va a adquirir al proveedor.",
    "leadership_change": "Hay un cambio en la dirección del proveedor.",
    "cyber_incident": "Un ciberataque afecta a los sistemas del proveedor.",
    "utility_outage": "Un corte de electricidad o de agua afecta al proveedor.",
    "supply_shortage": "El proveedor anuncia escasez o retrasos en sus envíos.",
    "geopolitical_conflict": "Un conflicto geopolítico afecta a la zona del proveedor.",
    "other_risk": "Un evento puede afectar al suministro del proveedor.",
}
EVENT_SHORT = {
    "fire_plant_incident": "incendio en planta", "natural_disaster": "desastre natural", "labour_strike": "huelga",
    "logistics_disruption": "interrupción logística", "regulatory_action": "acción del regulador",
    "quality_recall": "retirada de lotes", "export_restriction": "restricción a la exportación",
    "financial_distress": "dificultades financieras", "acquisition": "adquisición por un competidor",
    "leadership_change": "cambio de dirección", "cyber_incident": "ciberataque", "utility_outage": "corte de suministros",
    "supply_shortage": "escasez de suministro", "geopolitical_conflict": "conflicto geopolítico",
    "other_risk": "otro riesgo",
}


# ---------------------------------------------------------------------------
# Formatos
# ---------------------------------------------------------------------------

def signed(x: float) -> str:
    """+9 / −44 con el signo menos tipográfico del mockup."""
    v = round(x)
    return f"+{v}" if v > 0 else ("0" if v == 0 else f"−{abs(v)}")


def meur(x: float, dec: int = 1) -> str:
    return f"{x / 1e6:.{dec}f}".replace(".", ",")


def pct(x: float, dec: int = 0) -> str:
    return f"{x * 100:.{dec}f}".replace(".", ",") + " %"


def when(iso: str) -> str:
    meses = "ene feb mar abr may jun jul ago sep oct nov dic".split()
    try:
        d = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    return f"{d.day} {meses[d.month - 1]} {d.year}, {d:%H:%M}"


def duration_es(reported: str) -> str:
    """'12 weeks' -> '12 semanas'; '1 months' -> '1 mes'."""
    m = re.match(r"([\d.]+)\s+(\w+)", reported or "")
    if not m or m.group(2) not in UNIT_ES:
        return reported or ""
    v = float(m.group(1))
    one, many = UNIT_ES[m.group(2)]
    return f"{v:g} {one if v == 1 else many}"


def margin_color(margin: float, level: str) -> str:
    if level == "vigilar":
        return "#5B5766"
    if margin < 0:
        return "#B3261E"
    return "#8A5A00" if margin < MARGIN_TIGHT_DAYS else "#2E7D4F"


def highlight_duration(text: str, reported: str) -> tuple[str, bool]:
    """Escapa el texto y resalta la duración citada (<mark>). Devuelve (html, ¿encontrada?)."""
    esc = html.escape(text or "")
    m = re.match(r"([\d.]+)\s+(\w+)", reported or "")
    if not m:
        return esc, False
    value, stem = float(m.group(1)), UNIT_STEMS.get(m.group(2), "day")
    nums = [re.escape(f"{value:g}")] + [w for w, n in NUMBER_WORDS.items() if n == value]
    rx = re.compile(rf"\b(?:up to\s+)?(?:{'|'.join(nums)})[\s-]+{stem}s?\b", re.I)
    out, found = rx.subn(lambda x: f"<mark>{x.group(0)}</mark>", esc)
    return out, found > 0


def quote_for(r: dict) -> tuple[str, bool]:
    """La frase de la noticia que se cita: la evidencia del juez o, si no contiene la duración, la frase
    del resumen que la contiene."""
    evidence = r.get("evidence") or ""
    q, ok = highlight_duration(evidence, r.get("recovery_reported", ""))
    if ok or not r.get("recovery_reported"):
        return q, ok
    for sent in re.split(r"(?<=[.!?])\s+", r.get("summary") or ""):
        q2, ok2 = highlight_duration(sent, r["recovery_reported"])
        if ok2:
            return q2, True
    return q, False


# ---------------------------------------------------------------------------
# Alertas
# ---------------------------------------------------------------------------

@dataclass
class Alert:
    r: dict
    level: str
    worst: Countdown
    supplier: Supplier
    others: list[Countdown] = field(default_factory=list)

    @property
    def id(self) -> str:
        return self.r["news_id"]

    @property
    def margin(self) -> float:
        return self.worst.margin_days

    @property
    def estimated(self) -> bool:
        return self.worst.ttr_estimated

    @property
    def case(self) -> str:
        return situation(self.worst, self.supplier)

    @property
    def products(self) -> list[str]:
        out: list[str] = []
        for c in [self.worst] + self.others:
            out += [p for p in c.products if p not in out]
        return out

    @property
    def place(self) -> str:
        return place_es(self.supplier.city, self.supplier.country)

    @property
    def what_short(self) -> str:
        """'escasez de suministro · 12 semanas'."""
        ev = EVENT_SHORT.get(self.r["event_type"], self.r.get("event_label", ""))
        d = duration_es(self.r.get("recovery_reported", ""))
        return f"{ev} · {d}" if d else ev

    @property
    def affects_note(self) -> str:
        """Tercera línea de la tarjeta de la cola: por qué preocupa."""
        if self.r.get("needs_review") and self.level != "critica":
            return "requiere revisión humana"
        return {"unico_deficit": "proveedor único", "alt_tarde": "alternativo no llega a tiempo",
                "alt_afectado": "alternativo también afectado", "sin_stock_unico": "servicio único sin reserva",
                "sin_stock_alt": "sin stock de reserva", "sin_stock_alt_afectado": "sin stock ni alternativo",
                }.get(self.case, "proveedor único" if self.supplier.single_source else "con alternativo")

    def what(self) -> str:
        """Dos frases: qué pasa y cómo queda el suministro."""
        s, c = self.supplier, self.worst
        alt = s.alternate_name or s.alternate_id
        first = EVENT_WHAT.get(self.r["event_type"], EVENT_WHAT["other_risk"])
        second = {
            "unico_deficit": "No hay ningún alternativo aprobado para este material.",
            "alt_tarde": f"Su alternativo, {alt}, tarda {c.alternate_lead_days or 0:.0f} días en entregar: no llega "
                         "antes de que se acabe el stock.",
            "alt_afectado": f"Su alternativo, {alt}, está afectado por el mismo evento.",
            "alt_a_tiempo": f"Su alternativo, {alt}, puede entregar en {c.alternate_lead_days or 0:.0f} días.",
            "alt_insuficiente": f"Su alternativo, {alt}, puede entregar en {c.alternate_lead_days or 0:.0f} días, "
                                "pero no basta para cubrir toda la recuperación.",
            "cubre": "El stock actual cubre la recuperación prevista.",
            "sin_corte": "No se espera una interrupción del suministro a corto plazo.",
        }.get(self.case, "No hay stock de reserva: el impacto es inmediato.")
        more = ""
        if self.others:
            names = ", ".join(short_supplier(load_suppliers()[o.supplier_id].name) for o in self.others)
            more = f" También afecta a {names}."
        return f"{first} {second}{more}"


def _countdown(d: dict) -> Countdown:
    return Countdown(**d)


def build_alerts(results: list[dict]) -> list[Alert]:
    sup = load_suppliers()
    out = []
    for r in results:
        if not r.get("is_risk") or not r.get("countdown"):
            continue
        cds = [_countdown(d) for d in r["countdown"]]
        worst = min(cds, key=lambda c: (c.margin_days, c.supplier_id))
        if r["urgent"]:
            level = "critica"
        elif any(c.status == "riesgo_latente" for c in cds):
            level = "vigilar"
        else:
            level = "seguimiento"
        out.append(Alert(r, level, worst, sup[worst.supplier_id], [c for c in cds if c is not worst]))
    out.sort(key=lambda a: (LEVEL_ORDER[a.level], a.margin, a.id))
    return out


def status_chip(a: Alert) -> tuple[str, str]:
    """(texto, color) del chip de la alerta."""
    if a.level == "critica":
        tail = {"rotura_prevista": " · ROTURA PREVISTA", "sin_inventario": " · IMPACTO INMEDIATO",
                "margen_ajustado": " · MARGEN AJUSTADO"}.get(a.worst.status, "")
        return "● CRÍTICA" + tail, "red"
    if a.level == "vigilar":
        return "▲ VIGILAR · RIESGO LATENTE", "amber"
    return "SEGUIMIENTO SEMANAL", "grey"

