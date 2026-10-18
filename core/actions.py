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


def supplier_action(c: Countdown, s: Supplier) -> str:
    """Acción para un proveedor afectado según su cuenta atrás."""
    head = f"{s.id} ({s.material})"
    alt = f"{s.alternate_id} {s.alternate_name}" if s.alternate_id else ""

    # Sin inventario de reserva (logística, servicios): no hay colchón
    if c.inventory_days is None:
        if c.ttr_days == 0:
            return f"{head}: sin interrupción a corto plazo; vigilar la evolución."
        if s.alternate_id and not c.alternate_affected:
            lead = f" (plazo {c.alternate_lead_days:.0f} d)" if c.alternate_lead_days is not None else ""
            return (f"{head}: sin inventario de reserva, impacto inmediato durante {_ttr(c)}. "
                    f"Derivar los envíos al alternativo {alt}{lead}.")
        if c.alternate_affected:
            return (f"{head}: sin inventario de reserva y su alternativo {s.alternate_id} también está afectado. "
                    f"Contratar un servicio puntual fuera de la zona afectada durante {_ttr(c)}.")
        return (f"{head}: servicio ÚNICO sin reserva, impacto inmediato durante {_ttr(c)}. Activar el plan de "
                "contingencia y buscar un sustituto puntual.")

    inv = c.inventory_days
    # El inventario por sí solo cubre la recuperación: el alternativo no hace falta
    if inv >= c.ttr_days:
        if c.ttr_days == 0:
            return f"{head}: sin interrupción a corto plazo; vigilar la evolución."
        reserve = (f" El alternativo {s.alternate_id} queda en reserva." if s.alternate_id and not c.alternate_affected
                   else "")
        unique = "proveedor ÚNICO; " if s.single_source else ""
        return (f"{head}: {unique}el inventario ({inv:.0f} d) cubre por sí solo la recuperación prevista "
                f"({_ttr(c)}), margen {inv - c.ttr_days:+.0f} d. Confirmar el stock real y la fecha de "
                f"reanudación.{reserve}")

    # Hace falta algo más que el inventario
    if s.single_source or not s.alternate_id:
        why = "proveedor ÚNICO, sin alternativo aprobado" if s.single_source else "sin alternativo"
        return (f"{head}: {why}; el inventario ({inv:.0f} d) no llega a la recuperación prevista ({_ttr(c)}): "
                + _deficit_plan(c, s))
    if c.alternate_affected:
        return (f"{head}: su alternativo {s.alternate_id} también está afectado por el mismo evento, así que no es "
                f"una salida; el inventario ({inv:.0f} d) no llega a la recuperación ({_ttr(c)}): "
                + _deficit_plan(c, s))
    if c.alternate_in_time:
        if c.margin_days >= 0:
            return (f"{head}: activar YA el alternativo {alt}: entrega en {c.alternate_lead_days:.0f} d, antes de que "
                    f"se acabe el inventario ({inv:.0f} d); con él se llega a la recuperación ({_ttr(c)}) con "
                    f"margen {c.margin_days:+.0f} d.")
        return (f"{head}: activar YA el alternativo {alt} (entrega en {c.alternate_lead_days:.0f} d), pero no basta: "
                + _deficit_plan(c, s))
    lead = f"tarda {c.alternate_lead_days:.0f} d" if c.alternate_lead_days is not None else "no tiene plazo conocido"
    return (f"{head}: el alternativo {s.alternate_id} {lead} y el inventario dura {inv:.0f} d, así que no llega a "
            f"tiempo como solución principal; la recuperación prevista es de {_ttr(c)}: "
            + _deficit_plan(c, s, first=f"pedir a {s.alternate_id} un envío urgente para acortar su plazo"))


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
