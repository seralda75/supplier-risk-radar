"""Calendario de pedidos: qué medicamentos tienen stock suficiente, cuáles están en peligro y cuáles se
quedan sin stock, y hasta qué día se puede esperar para pedir. Es una proyección desde hoy.

Supuesto: la reposición es continua. Salvo los proveedores con una alerta activa, hay pedidos regulares en
tránsito y el stock se mantiene; los días de cobertura de esos materiales se muestran solo como información.

Por material (hoja Materials: proveedor principal y alternativo), solo si una alerta activa (no descartada
como falsa alarma) para a su proveedor principal o alternativo:
- Estado: «rotura» si la alerta da margen negativo; «peligro» si es un riesgo latente (alerta no urgente con
  margen negativo) o el margen es de 0 a MARGEN_AJUSTADO días. Con más margen, el material queda cubierto.
- Fecha límite para pedir, si el stock propio se acaba antes de que el proveedor se recupere (si no, no hace
  falta pedir) = día en que se acaba el stock − plazo de entrega del alternativo; sin alternativo
  (o si también está afectado), − URGENTE_DIAS, el plazo de la compra puntual con cualificación de urgencia
  que propone el plan. Si ya ha pasado: pedir hoy con envío urgente, y se dice cuántos días tarde llegaría.
- De la cuenta atrás: día previsto de rotura, día de recuperación del proveedor y llegada del alternativo.
Sin alerta: «suficiente».

Un medicamento toma el peor estado de sus materiales. Quien llama pasa solo las cuentas atrás de las alertas
activas (sin las falsas alarmas).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache

import pandas as pd

from .config import TRAIN_XLSX
from .countdown import MARGIN_TIGHT_DAYS, Countdown
from .suppliers import load_suppliers

MARGEN_AJUSTADO = MARGIN_TIGHT_DAYS   # 14 días: margen de una alerta por debajo del cual hay peligro
URGENTE_DIAS = 7                      # compra puntual con cualificación de urgencia (plan: «1 semana»)
STATUS_ORDER = {"rotura": 0, "peligro": 1, "suficiente": 2}
STATUS_ES = {"rotura": "Rotura prevista", "peligro": "En peligro", "suficiente": "Suficiente"}


@dataclass(frozen=True)
class Material:
    id: str
    name: str
    primary_id: str
    alternate_id: str | None
    products: tuple[str, ...]
    monthly: str               # «3500 kg»


@lru_cache(maxsize=1)
def materials() -> tuple[Material, ...]:
    df = pd.read_excel(TRAIN_XLSX, sheet_name="Materials")
    out = []
    for m in df.itertuples(index=False):
        alt = None if pd.isna(m.Alternate_Supplier_ID) else m.Alternate_Supplier_ID
        prods = tuple(x.strip() for x in str(m.Used_In_Products).split(";") if x.strip())
        out.append(Material(m.Material_ID, m.Material, m.Primary_Supplier_ID, alt, prods,
                            f"{m.Monthly_Requirement:g} {m.Unit}"))
    return tuple(out)


@dataclass
class MaterialPlan:
    material: Material
    status: str                     # rotura | peligro | suficiente
    why: str                        # el motivo del estado, en una frase
    supplier_id: str                # el proveedor al que se pediría
    using_alternate: bool           # el afectado tiene un alternativo libre: se pediría a él
    stock_days: float               # días de cobertura del stock (información)
    affected: bool = False          # una alerta activa para a su proveedor principal o alternativo
    lead_days: float | None = None  # plazo del pedido de emergencia (alternativo o compra urgente)
    urgent_buy: bool = False        # sin alternativo libre: compra puntual con cualificación de urgencia
    deadline: date | None = None    # último día para pedir (solo con alerta)
    days_left: int | None = None    # días hasta la fecha límite (negativo: ya no llega a tiempo)
    margin: float | None = None     # margen de la alerta
    stockout: date | None = None    # día previsto de rotura (solo con margen negativo)
    recovery: date | None = None    # día en que se recupera el proveedor afectado
    alt_arrival: date | None = None  # día en que llegaría el primer envío del alternativo
    alert_supplier: str | None = None  # el proveedor afectado por la alerta

    @property
    def late_days(self) -> int:
        """Días que llegaría tarde un pedido hecho hoy (0 si aún hay tiempo)."""
        return max(0, -(self.days_left or 0))


@dataclass
class MedicinePlan:
    name: str
    status: str
    worst: MaterialPlan             # el material que decide el estado
    materials: list[MaterialPlan] = field(default_factory=list)
    today: date = date.min

    @property
    def deadline_plan(self) -> MaterialPlan | None:
        """El material con alerta cuya fecha límite para pedir llega antes (None si ninguno tiene alerta)."""
        hit = [m for m in self.materials if m.deadline]
        return min(hit, key=lambda m: m.deadline) if hit else None

    @property
    def deadline(self) -> date | None:
        p = self.deadline_plan
        return p.deadline if p else None

    @property
    def stockout_days(self) -> int | None:
        """Días hasta la rotura prevista (None si no se prevé rotura)."""
        days = [(m.stockout - self.today).days for m in self.materials if m.stockout]
        return min(days) if days else None

    @property
    def cover_days(self) -> float:
        """Días de cobertura del material con menos stock (información)."""
        return min(m.stock_days for m in self.materials)


def _affected(c: Countdown) -> bool:
    return c.ttr_days > 0                  # una alerta «sin corte» no para el suministro


def material_plan(m: Material, cds: list[Countdown], today: date) -> MaterialPlan:
    """Plan de un material con las cuentas atrás de las alertas activas (de cualquier proveedor)."""
    sup = load_suppliers()
    p = sup[m.primary_id]
    mine = [c for c in cds if c.supplier_id in (m.primary_id, m.alternate_id) and _affected(c)]
    if not mine:
        stock = float(p.inventory_cover_days or 0)
        return MaterialPlan(m, "suficiente", f"sin alertas: reposición regular ({stock:.0f} d de cobertura)",
                            m.primary_id, False, stock)
    w = min(mine, key=lambda c: c.margin_days)          # la alerta más comprometida
    hit = {c.supplier_id for c in mine}
    # A quién se pediría: el alternativo del afectado si existe y no está afectado; si no, compra urgente
    alt = w.alternate_id if w.alternate_id and w.alternate_id not in hit and not w.alternate_affected else None
    lead = float(w.alternate_lead_days if alt and w.alternate_lead_days is not None else URGENTE_DIAS)
    stock = float(w.inventory_days or 0)
    plan = MaterialPlan(m, "suficiente", "", alt or w.supplier_id, bool(alt), stock, affected=True,
                        margin=w.margin_days, alert_supplier=w.supplier_id,
                        recovery=today + timedelta(days=int(w.ttr_days)))
    # Solo hay que pedir si el stock propio se acaba antes de que el proveedor se recupere: entonces hay un día
    # de rotura y la fecha límite es ese día menos el plazo del pedido de emergencia
    if w.inventory_days is None or w.ttr_days > w.inventory_days:
        stock_end = today + timedelta(days=int(stock))   # se acaba el stock propio del proveedor afectado
        plan.lead_days, plan.urgent_buy = lead, alt is None
        plan.deadline = stock_end - timedelta(days=int(lead))
        plan.days_left = (plan.deadline - today).days
        if alt and w.alternate_lead_days is not None:     # si se pide hoy al alternativo, su primer envío
            plan.alt_arrival = today + timedelta(days=int(w.alternate_lead_days))
    if w.ttr_days > w.tts_days:
        plan.stockout = today + timedelta(days=int(w.tts_days))
    name = sup[w.supplier_id].name
    if w.status == "riesgo_latente":
        plan.status = "peligro"
        plan.why = f"riesgo latente en {name}: alerta no urgente con margen de {round(w.margin_days)} días"
    elif w.margin_days < 0:
        plan.status = "rotura"
        plan.why = f"alerta activa en {name} con margen de {round(w.margin_days)} días"
    elif w.margin_days <= MARGEN_AJUSTADO:
        plan.status = "peligro"
        plan.why = f"alerta activa en {name} con solo {round(w.margin_days)} días de margen"
    else:
        plan.why = f"alerta activa en {name}, pero cubierta: {round(w.margin_days)} días de margen"
    return plan


def plan(cds: list[Countdown], today: date | None = None) -> tuple[list[MaterialPlan], list[MedicinePlan]]:
    """Materiales y medicamentos, del peor al mejor. cds: cuentas atrás de las alertas activas."""
    today = today or date.today()
    mats = [material_plan(m, cds, today) for m in materials()]
    by_med: dict[str, list[MaterialPlan]] = {}
    for mp in mats:
        for p in mp.material.products:
            by_med.setdefault(p, []).append(mp)
    # Del peor al mejor: estado, fecha límite más próxima, con alerta antes que sin ella y menos cobertura
    key = lambda x: (STATUS_ORDER[x.status], x.days_left if x.days_left is not None else 10**6,   # noqa: E731
                     not x.affected, x.stock_days)
    meds = []
    for name, ms in by_med.items():
        ms = sorted(ms, key=key)
        meds.append(MedicinePlan(name, ms[0].status, ms[0], ms, today=today))
    mats.sort(key=key)
    meds.sort(key=lambda x: (STATUS_ORDER[x.status], (x.deadline - today).days if x.deadline else 10**6, x.name))
    return mats, meds
