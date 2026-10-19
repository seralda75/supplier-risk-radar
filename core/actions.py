"""Acción recomendada a partir de los datos y de la cuenta atrás (no inventada por el LLM).

    recommend_action(assessment, urgent, countdowns) -> texto para el comprador

La acción depende del margen de cada proveedor afectado (core/countdown.py):
- Si el inventario cubre la recuperación prevista: confirmar stock y fecha de reanudación; el
  alternativo queda en reserva.
- Si el alternativo aprobado llega antes de que se acabe el inventario y no está afectado: activarlo.
- Si el alternativo NO llega a tiempo, también está afectado o no existe, no se propone como solución
  principal: se indican los días de déficit y medidas coherentes (envío urgente del alternativo, compra
  puntual con cualificación de urgencia, reasignar stock, priorizar productos).
- Proveedores sin inventario (logística, servicios): el impacto es inmediato; se deriva al alternativo
  si no está afectado.

Es información para el comprador: no cambia ninguna respuesta Y/N ni la urgencia.
"""
from __future__ import annotations

from dataclasses import dataclass

from .countdown import Countdown, countdown
from .schemas import NewsAssessment
from .suppliers import Supplier, load_suppliers

SPOT_BUY = ("compra puntual a un fabricante fuera de la lista aprobada (requiere cualificación de urgencia "
            "por Calidad)")
REALLOCATE = "reasignar stock entre plantas y almacenes de Helixa"


def _prioritise(products: list[str]) -> str:
    if not products:
        return "priorizar los pedidos más críticos"
    if len(products) == 1:
        return f"reservar el stock restante para {products[0]} y escalonar las entregas"
    return f"repartir el stock restante priorizando los productos críticos ({', '.join(products)})"


def _ttr(c: Countdown) -> str:
    return f"{c.ttr_days} d{' estimados' if c.ttr_estimated else ''}"


def _deficit_plan(c: Countdown, s: Supplier, first: str = "") -> str:
    """Medidas para cubrir un déficit cuando el alternativo no es la solución (o no basta)."""
    steps = ([first] if first else []) + [SPOT_BUY, REALLOCATE, _prioritise(c.products)]
    return f"déficit de {c.deficit_days:.0f} días. Medidas: " + "; ".join(steps) + "."


def situation(c: Countdown, s: Supplier) -> str:
    """Situación del proveedor según su cuenta atrás. Una sola decisión para el texto y para el plan:
    sin_corte · cubre · alt_a_tiempo · alt_insuficiente · alt_tarde · alt_afectado · unico_deficit ·
    sin_stock_alt · sin_stock_alt_afectado · sin_stock_unico."""
    if c.ttr_days == 0:
        return "sin_corte"
    if c.inventory_days is None:              # logística y servicios: sin colchón de inventario
        if s.alternate_id and not c.alternate_affected:
            return "sin_stock_alt"
        return "sin_stock_alt_afectado" if c.alternate_affected else "sin_stock_unico"
    if c.inventory_days >= c.ttr_days:        # el inventario por sí solo cubre la recuperación
        return "cubre"
    if s.single_source or not s.alternate_id:
        return "unico_deficit"
    if c.alternate_affected:
        return "alt_afectado"
    if c.alternate_in_time:
        return "alt_a_tiempo" if c.margin_days >= 0 else "alt_insuficiente"
    return "alt_tarde"


def supplier_action(c: Countdown, s: Supplier) -> str:
    """Acción para un proveedor afectado según su cuenta atrás (texto para el detalle y la auditoría)."""
    head = f"{s.id} ({s.material})"
    alt = f"{s.alternate_id} {s.alternate_name}" if s.alternate_id else ""
    inv = c.inventory_days
    case = situation(c, s)
    if case == "sin_corte":
        return f"{head}: sin interrupción a corto plazo; vigilar la evolución."
    if case == "sin_stock_alt":
        lead = f" (plazo {c.alternate_lead_days:.0f} d)" if c.alternate_lead_days is not None else ""
        return (f"{head}: sin inventario de reserva, impacto inmediato durante {_ttr(c)}. "
                f"Derivar los envíos al alternativo {alt}{lead}.")
    if case == "sin_stock_alt_afectado":
        return (f"{head}: sin inventario de reserva y su alternativo {s.alternate_id} también está afectado. "
                f"Contratar un servicio puntual fuera de la zona afectada durante {_ttr(c)}.")
    if case == "sin_stock_unico":
        return (f"{head}: servicio ÚNICO sin reserva, impacto inmediato durante {_ttr(c)}. Activar el plan de "
                "contingencia y buscar un sustituto puntual.")
    if case == "cubre":
        reserve = (f" El alternativo {s.alternate_id} queda en reserva." if s.alternate_id and not c.alternate_affected
                   else "")
        unique = "proveedor ÚNICO; " if s.single_source else ""
        return (f"{head}: {unique}el inventario ({inv:.0f} d) cubre por sí solo la recuperación prevista "
                f"({_ttr(c)}), margen {inv - c.ttr_days:+.0f} d. Confirmar el stock real y la fecha de "
                f"reanudación.{reserve}")
    if case == "unico_deficit":
        why = "proveedor ÚNICO, sin alternativo aprobado" if s.single_source else "sin alternativo"
        return (f"{head}: {why}; el inventario ({inv:.0f} d) no llega a la recuperación prevista ({_ttr(c)}): "
                + _deficit_plan(c, s))
    if case == "alt_afectado":
        return (f"{head}: su alternativo {s.alternate_id} también está afectado por el mismo evento, así que no es "
                f"una salida; el inventario ({inv:.0f} d) no llega a la recuperación ({_ttr(c)}): "
                + _deficit_plan(c, s))
    if case == "alt_a_tiempo":
        return (f"{head}: activar YA el alternativo {alt}: entrega en {c.alternate_lead_days:.0f} d, antes de que "
                f"se acabe el inventario ({inv:.0f} d); con él se llega a la recuperación ({_ttr(c)}) con "
                f"margen {c.margin_days:+.0f} d.")
    if case == "alt_insuficiente":
        return (f"{head}: activar YA el alternativo {alt} (entrega en {c.alternate_lead_days:.0f} d), pero no basta: "
                + _deficit_plan(c, s))
    lead = f"tarda {c.alternate_lead_days:.0f} d" if c.alternate_lead_days is not None else "no tiene plazo conocido"
    return (f"{head}: el alternativo {s.alternate_id} {lead} y el inventario dura {inv:.0f} d, así que no llega a "
            f"tiempo como solución principal; la recuperación prevista es de {_ttr(c)}: "
            + _deficit_plan(c, s, first=f"pedir a {s.alternate_id} un envío urgente para acortar su plazo"))


# ---------------------------------------------------------------------------
# Plan en pasos (para el director de compras): qué hacer, quién y cuándo
# ---------------------------------------------------------------------------

@dataclass
class Step:
    text: str
    owner: str            # Compras, Planificación, Calidad, Logística, Operaciones
    when: str             # hoy, 48 h, 1 semana...


# Plazos: si la alerta no es urgente, todo puede esperar a la revisión semanal
_RELAXED = {"hoy": "esta semana", "48 h": "esta semana", "1 semana": "2 semanas"}


def plan_steps(c: Countdown, s: Supplier, urgent: bool = True) -> list[Step]:
    """Plan en pasos para un proveedor, con la misma lógica (situation) que supplier_action.
    Lenguaje de negocio: nombres de proveedor y de medicamento, sin IDs ni siglas."""
    from .labels import product_es
    name, alt = s.name, s.alternate_name or s.alternate_id or ""
    prods = " y ".join(product_es(p) for p in c.products) if c.products else "los pedidos más críticos"
    deficit = f"{c.deficit_days:.0f} días"
    case = situation(c, s)
    steps: list[Step]
    if case == "sin_corte":
        steps = [Step(f"Vigilar la evolución de {name} en el informe semanal", "Compras", "semanal")]
    elif case == "cubre":
        steps = [Step(f"Confirmar con {name} el stock real y la fecha de reanudación", "Compras", "hoy")]
        if s.alternate_id and not c.alternate_affected:
            steps.append(Step(f"Mantener a {alt} en reserva: con el stock actual no hace falta activarlo",
                              "Compras", "si se alarga"))
    elif case == "alt_a_tiempo":
        steps = [Step(f"Activar el pedido a {alt}: entrega en {c.alternate_lead_days:.0f} días, antes de que se "
                      "acabe el stock", "Compras", "hoy"),
                 Step(f"Confirmar con {name} la fecha de reanudación", "Compras", "48 h")]
    elif case == "alt_insuficiente":
        steps = [Step(f"Activar el pedido a {alt} (entrega en {c.alternate_lead_days:.0f} días); aun así faltan "
                      f"{deficit}", "Compras", "hoy"),
                 Step(f"Reservar el stock disponible para {prods}", "Planificación", "48 h"),
                 Step("Compra puntual a un fabricante no aprobado, con cualificación de urgencia", "Calidad",
                      "1 semana")]
    elif case == "alt_tarde":
        steps = [Step(f"Pedir a {alt} un envío urgente: con su plazo habitual ({c.alternate_lead_days:.0f} días) "
                      "no llega antes de que se acabe el stock", "Compras", "hoy"),
                 Step(f"Reservar el stock disponible para {prods} (faltan {deficit})", "Planificación", "48 h"),
                 Step("Reasignar stock entre plantas y almacenes de Helixa", "Logística", "48 h"),
                 Step("Compra puntual a un fabricante no aprobado, con cualificación de urgencia", "Calidad",
                      "1 semana")]
    elif case in ("unico_deficit", "alt_afectado"):
        first = (f"Confirmar con {name} la fecha real y pedir una asignación parcial" if case == "unico_deficit"
                 else f"Confirmar con {name} la fecha real: su alternativo {alt} está afectado por el mismo evento")
        steps = [Step(first, "Compras", "hoy"),
                 Step(f"Reservar el stock disponible para {prods} (faltan {deficit})", "Planificación", "48 h"),
                 Step("Iniciar la cualificación de emergencia de un proveedor alternativo"
                      + (" fuera de la zona afectada" if case == "alt_afectado" else ""), "Calidad", "1 semana")]
    elif case == "sin_stock_alt":
        steps = [Step(f"Derivar los envíos a {alt}"
                      + (f" (plazo {c.alternate_lead_days:.0f} días)" if c.alternate_lead_days is not None else ""),
                      "Logística", "hoy"),
                 Step(f"Confirmar con {name} cuándo se restablece el servicio", "Compras", "48 h")]
    elif case == "sin_stock_alt_afectado":
        steps = [Step(f"Contratar un servicio puntual fuera de la zona afectada durante {c.ttr_days} días",
                      "Logística", "hoy")]
    else:   # sin_stock_unico
        steps = [Step(f"Activar el plan de contingencia: sin {name} el impacto es inmediato", "Operaciones", "hoy"),
                 Step("Buscar un sustituto puntual", "Compras", "1 semana")]
    if not urgent:
        steps = [Step(x.text, x.owner, _RELAXED.get(x.when, x.when)) for x in steps]
    return steps


def recommend_action(a: NewsAssessment, urgent: bool, cds: list[Countdown] | None = None) -> str:
    """Acción para el comprador: un párrafo por proveedor afectado, del menor margen al mayor."""
    if not a.is_risk:
        return "Ninguna acción: no afecta al suministro."
    cds = countdown(a, urgent) if cds is None else cds
    sup = load_suppliers()
    cds = sorted(cds, key=lambda c: (c.inventory_days is None, c.margin_days))
    lines = [supplier_action(c, sup[c.supplier_id]) for c in cds]
    if urgent:
        prefix = "ACTUAR YA."
    elif any(c.status == "riesgo_latente" for c in cds):
        prefix = "No urgente, pero con riesgo latente (margen negativo): revisarlo esta semana."
    else:
        prefix = "Seguimiento en el informe semanal."
    return " ".join([prefix] + lines)
