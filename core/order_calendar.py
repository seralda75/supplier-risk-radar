"""Calendario de pedidos: hasta qué día se puede esperar para pedir cada material, y cómo está cada
medicamento. Es una proyección desde hoy con los datos del reto y las alertas activas.

Por material (hoja Materials: proveedor principal y alternativo):
- Proveedor que se usaría: el principal o, si una alerta activa lo afecta (y el alternativo no lo está),
  el alternativo.
- Fecha límite para pedir = hoy + (días de stock − plazo de entrega de ese proveedor). Después, el pedido
  llega cuando el stock ya se ha acabado.
- De la cuenta atrás de la alerta (si la hay): día previsto de rotura, día de recuperación del proveedor y
  día en que llega el primer envío del alternativo.
- Estado: «rotura» si una alerta activa da margen negativo; «peligro» si el stock no llega al plazo de
  entrega + PELIGRO_DIAS o si una alerta da un margen de 0 a MARGEN_AJUSTADO días; «suficiente» si no.

Un medicamento toma el peor estado de sus materiales. Las alertas descartadas como falsa alarma no llegan
aquí: quien llama pasa solo las cuentas atrás de las alertas activas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache

import pandas as pd

from .config import TRAIN_XLSX
from .countdown import Countdown
from .suppliers import load_suppliers

PELIGRO_DIAS = 7              # colchón sobre el plazo de entrega
MARGEN_AJUSTADO = 14          # margen de una alerta (días) por debajo del cual hay peligro
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
    using_alternate: bool           # el principal está afectado y se pediría al alternativo
    stock_days: float
    lead_days: float
    deadline: date                  # último día para pedir (puede ser anterior a hoy: ya no llega)
    days_left: int                  # días hasta la fecha límite (negativo: vencida)
    margin: float | None = None     # margen de la alerta (None si no hay alerta)
    stockout: date | None = None    # día previsto de rotura (solo con margen negativo)
    recovery: date | None = None    # día en que se recupera el proveedor afectado
    alt_arrival: date | None = None  # día en que llega el primer envío del alternativo
    alert_supplier: str | None = None  # el proveedor afectado por la alerta


@dataclass
class MedicinePlan:
    name: str
    status: str
    worst: MaterialPlan             # el material que decide el estado
    materials: list[MaterialPlan] = field(default_factory=list)

    @property
    def deadline(self) -> date:
        return min(m.deadline for m in self.materials)

    @property
    def stockout_days(self) -> int | None:
        """Días hasta la rotura prevista (None si no se prevé rotura)."""
        days = [(m.stockout - self.today).days for m in self.materials if m.stockout]
        return min(days) if days else None

    today: date = date.min


def _affected(c: Countdown) -> bool:
    return c.ttr_days > 0


def material_plan(m: Material, cds: list[Countdown], today: date) -> MaterialPlan:
    """Plan de un material con las cuentas atrás de las alertas activas (de cualquier proveedor)."""
    sup = load_suppliers()
    mine = [c for c in cds if c.supplier_id in (m.primary_id, m.alternate_id) and _affected(c)]
    primary_hit = any(c.supplier_id == m.primary_id for c in mine)
    alt_hit = any(c.supplier_id == m.alternate_id for c in mine)
    use_alt = bool(m.alternate_id) and primary_hit and not alt_hit
    use = m.alternate_id if use_alt else m.primary_id
    p = sup[m.primary_id]
    stock = float(p.inventory_cover_days or 0)
    lead = float(sup[use].lead_time_days or p.lead_time_days or 0)
    deadline = today + timedelta(days=int(stock - lead))
    plan = MaterialPlan(m, "suficiente", "", use, use_alt, stock, lead, deadline, (deadline - today).days)
    if mine:
        w = min(mine, key=lambda c: c.margin_days)
        plan.margin, plan.alert_supplier = w.margin_days, w.supplier_id
        plan.recovery = today + timedelta(days=int(w.ttr_days))
        if w.ttr_days > w.tts_days:
            plan.stockout = today + timedelta(days=int(w.tts_days))
        if use_alt and w.alternate_lead_days is not None and not w.alternate_affected:
            plan.alt_arrival = today + timedelta(days=int(w.alternate_lead_days))
    if plan.margin is not None and plan.margin < 0:
        plan.status = "rotura"
        plan.why = f"alerta activa con margen de {round(plan.margin)} días"
    elif plan.margin is not None and plan.margin <= MARGEN_AJUSTADO:
        plan.status = "peligro"
        plan.why = f"alerta activa con solo {round(plan.margin)} días de margen"
    elif stock < lead + PELIGRO_DIAS:
        plan.status = "peligro"
        plan.why = f"el stock ({stock:.0f} d) apenas cubre el plazo de entrega ({lead:.0f} d) + {PELIGRO_DIAS} d"
    else:
        plan.why = f"el stock ({stock:.0f} d) cubre el plazo de entrega ({lead:.0f} d)"
    return plan


def plan(cds: list[Countdown], today: date | None = None) -> tuple[list[MaterialPlan], list[MedicinePlan]]:
    """Materiales y medicamentos, del peor al mejor. cds: cuentas atrás de las alertas activas."""
    today = today or date.today()
    mats = [material_plan(m, cds, today) for m in materials()]
    by_med: dict[str, list[MaterialPlan]] = {}
    for mp in mats:
        for p in mp.material.products:
            by_med.setdefault(p, []).append(mp)
    meds = []
    for name, ms in by_med.items():
        ms = sorted(ms, key=lambda x: (STATUS_ORDER[x.status], x.days_left))
        meds.append(MedicinePlan(name, ms[0].status, ms[0], ms, today=today))
    key = lambda x: (STATUS_ORDER[x.status], x.days_left)          # noqa: E731
    mats.sort(key=key)
    meds.sort(key=lambda x: (STATUS_ORDER[x.status], (x.deadline - today).days, x.name))
    return mats, meds
