"""Cuenta atrás: ¿aguanta Helixa hasta que el proveedor afectado se recupere?

    countdown(assessment) -> [Countdown por proveedor afectado]

- TTS (time to survive): días que Helixa puede seguir produciendo sin ese proveedor.
- TTR (time to recover): días hasta que el proveedor vuelve a la normalidad (duración que da la
  noticia, recovery_value + recovery_unit del juez, convertida a días por código).
- Margen = TTS − TTR. Negativo -> rotura de stock prevista: hay que actuar ya.
  Si la noticia NO es urgente pero el margen es negativo -> riesgo latente: no salta la alerta
  (la urgencia es gravedad × dependencia y no depende de esta cuenta), pero el comprador lo ve,
  junto con si el TTR viene de la noticia o es un valor por defecto.

Supuestos (visibles y ajustables por el cliente):
1. Sin alternativo, TTS = Inventory_Cover_Days (el inventario se consume al ritmo habitual).
2. Con un alternativo aprobado que NO esté afectado por el mismo evento: como ya está cualificado,
   se le hace un pedido el día 0; llega tras su Lead_Time_Days y desde entonces asume una parte del
   volumen (ALTERNATE_SHARE = 50 %, supuesto conservador de capacidad libre). El inventario que queda
   cuando llega el primer envío se consume más despacio y dura más:
       margen del alternativo = max(0, inventario − plazo del alternativo) × share / (1 − share)
   Si el plazo del alternativo supera el inventario, el alternativo no llega a tiempo: margen 0.
3. Proveedores sin inventario (logística, servicios): no hay colchón; el impacto es inmediato.
4. Si el juez no da recovery_days: si el evento no para el suministro a corto plazo (efecto lento),
   TTR = 0; si lo para, se usa un valor por defecto según el tipo de evento, marcado como estimado.
   Son órdenes de magnitud generales, no datos medidos: el cliente los sustituye por su histórico.

No cambia ninguna respuesta Y/N: es información para el comprador (y para el panel y el bot).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .schemas import EVENT_LABELS_ES, NewsAssessment
from .suppliers import Supplier, load_suppliers

ALTERNATE_SHARE = 0.5        # parte del volumen que puede asumir el alternativo aprobado
MARGIN_TIGHT_DAYS = 14       # por debajo, margen ajustado: ~2 semanas para gestionar un pedido urgente

# Días hasta la recuperación cuando la noticia no da pistas (órdenes de magnitud, no medidos)
DEFAULT_RECOVERY_DAYS = {
    "fire_plant_incident": 30,     # inspecciones y reparaciones de la planta
    "natural_disaster": 30,        # reapertura de fábricas y accesos
    "utility_outage": 14,
    "labour_strike": 7,
    "logistics_disruption": 14,
    "regulatory_action": 90,       # levantar una suspensión o una warning letter lleva meses
    "quality_recall": 30,          # investigación y liberación de lotes nuevos
    "export_restriction": 60,      # trámites de licencia o cambio de política
    "financial_distress": 90,
    "cyber_incident": 14,
    "geopolitical_conflict": 60,
    "supply_shortage": 30,
    "other_risk": 30,
    "acquisition": 0,              # no interrumpe el suministro por sí misma
    "leadership_change": 0,
}

STATUS_LABELS = {
    "rotura_prevista": "rotura de stock prevista",
    "riesgo_latente": "riesgo latente (no urgente, pero el margen es negativo)",
    "margen_ajustado": "margen ajustado",
    "cubierto": "cubierto",
    "sin_inventario": "sin inventario de reserva",
}


@dataclass
class Countdown:
    supplier_id: str
    supplier_name: str
    inventory_days: float | None
    alternate_id: str | None
    alternate_affected: bool
    alternate_margin_days: float
    tts_days: float
    ttr_days: int
    ttr_estimated: bool
    ttr_basis: str
    margin_days: float
    status: str
    products: list[str] = field(default_factory=list)
    monthly_requirement: str = ""
    note: str = ""

    def summary(self) -> str:
        """Una línea para el detalle del test, el bot y el panel."""
        ttr = f"{self.ttr_days} d{' (estimado)' if self.ttr_estimated else ''}"
        prods = ", ".join(self.products) or "sin productos registrados"
        if self.inventory_days is None:
            if self.ttr_days == 0:
                why = "efecto lento" if self.ttr_estimated else "según la noticia"
                return f"{self.supplier_id}: sin interrupción a corto plazo ({why}) · {prods}"
            return f"{self.supplier_id}: sin inventario de reserva, impacto inmediato durante {ttr} · {prods}"
        status = STATUS_LABELS[self.status]
        if self.status == "riesgo_latente":
            status += " · TTR estimado" if self.ttr_estimated else " · TTR según la noticia"
        return (f"{self.supplier_id}: TTS {self.tts_days:.0f} d − TTR {ttr} = {self.margin_days:+.0f} d · "
                f"{status} · {prods}")


def time_to_recover(a: NewsAssessment) -> tuple[int, bool, str]:
    """(días, ¿estimado?, de dónde sale)."""
    if a.recovery_days is not None:
        return a.recovery_days, False, "según la noticia (juez LLM)"
    if not a.stops_supply_soon:
        return 0, True, "efecto lento: no interrumpe el suministro a corto plazo"
    label = EVENT_LABELS_ES.get(a.event_type, a.event_type)
    return DEFAULT_RECOVERY_DAYS.get(a.event_type, 30), True, f"valor por defecto para {label}"


def alternate_margin(s: Supplier, affected: set[str]) -> tuple[float, bool, str]:
    """(días extra que da el alternativo, ¿alternativo también afectado?, nota)."""
    if not s.alternate_id:
        return 0.0, False, "proveedor único: sin alternativo aprobado" if s.single_source else "sin alternativo"
    if s.alternate_id in affected:
        return 0.0, True, f"el alternativo {s.alternate_id} también está afectado"
    alt = load_suppliers().get(s.alternate_id)
    lead = alt.lead_time_days if alt else None
    inv = s.inventory_cover_days or 0.0
    if lead is None:
        return 0.0, False, f"alternativo {s.alternate_id} sin plazo de entrega conocido"
    if lead >= inv:
        return 0.0, False, (f"el alternativo {s.alternate_id} tarda {lead:.0f} d en entregar: "
                            f"no llega antes de que se acabe el inventario")
    extra = (inv - lead) * ALTERNATE_SHARE / (1 - ALTERNATE_SHARE)
    return extra, False, f"el alternativo {s.alternate_id} entrega en {lead:.0f} d y asume el {ALTERNATE_SHARE:.0%}"


def supplier_countdown(s: Supplier, a: NewsAssessment, affected: set[str], urgent: bool = True) -> Countdown:
    ttr, estimated, basis = time_to_recover(a)
    extra, alt_affected, note = alternate_margin(s, affected)
    inv = s.inventory_cover_days
    tts = (inv or 0.0) + extra
    margin = tts - ttr
    if inv is None:
        status = "cubierto" if ttr == 0 else "sin_inventario"     # sin interrupción no hace falta colchón
    elif margin < 0:
        status = "rotura_prevista" if urgent else "riesgo_latente"
    elif margin < MARGIN_TIGHT_DAYS:
        status = "margen_ajustado"
    else:
        status = "cubierto"
    return Countdown(
        supplier_id=s.id, supplier_name=s.name, inventory_days=inv, alternate_id=s.alternate_id,
        alternate_affected=alt_affected, alternate_margin_days=round(extra, 1), tts_days=round(tts, 1),
        ttr_days=ttr, ttr_estimated=estimated, ttr_basis=basis, margin_days=round(margin, 1), status=status,
        products=list(s.products), monthly_requirement=s.monthly_requirement, note=note,
    )


def countdown(a: NewsAssessment, urgent: bool = True) -> list[Countdown]:
    """Cuenta atrás de cada proveedor afectado (vacía si la noticia no es un riesgo).
    `urgent` solo cambia la etiqueta de un margen negativo (rotura prevista o riesgo latente)."""
    if not a.is_risk:
        return []
    sup = load_suppliers()
    affected = set(a.affected_ids)
    return [supplier_countdown(sup[i], a, affected, urgent) for i in sorted(affected) if i in sup]


def worst(cds: list[Countdown]) -> Countdown | None:
    """El proveedor con menos margen (el que marca la urgencia de la compra)."""
    with_inventory = [c for c in cds if c.inventory_days is not None]
    return min(with_inventory, key=lambda c: c.margin_days) if with_inventory else (cds[0] if cds else None)


def as_dicts(cds: list[Countdown]) -> list[dict]:
    return [asdict(c) for c in cds]
