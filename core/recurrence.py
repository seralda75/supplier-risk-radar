"""Recurrencia de compra: con qué proveedores trabaja de forma habitual cada comprador.

Los datos del reto no traen historial de compras: data/purchase_history.csv es SINTÉTICO, generado por
scripts/build_purchase_history.py con semilla fija (ver docs/fase6_telegram.md).

Por proveedor (y, si se indica, por comprador): pedidos en los últimos 6 y 12 meses, meses seguidos con pedido,
último pedido y pedidos en tránsito (hechos y aún sin llegar). Un proveedor es **habitual** (recurrente) con al
menos RECURRENT_MIN pedidos en 6 meses: sus compradores reciben sus alertas sin tener que seguirlo.
"""
from __future__ import annotations

import calendar
import csv
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from .config import DATA_DIR

HISTORY_PATH = DATA_DIR / "purchase_history.csv"
RECURRENT_MIN = 3            # pedidos en 6 meses para ser proveedor habitual

# Compradores ficticios de Helixa, uno por área. Cada categoría de proveedor (hoja Suppliers) tiene un área.
BUYERS = {
    "B1": {"name": "Lucía Herrera", "area": "APIs y excipientes",
           "categories": ["API", "Excipients", "Chemicals", "Single-use bioprocess", "Lab reagents"]},
    "B2": {"name": "Pablo Navarro", "area": "Envases",
           "categories": ["Primary packaging", "Secondary packaging"]},
    "B3": {"name": "Irene Campos", "area": "Logística y servicios",
           "categories": ["Logistics", "Services", "Consumables"]},
}


def buyer_for(category: str) -> str:
    """El comprador responsable de una categoría de proveedor."""
    return next(b for b, d in BUYERS.items() if category in d["categories"])


@dataclass(frozen=True)
class Order:
    id: str
    day: date
    supplier_id: str
    material: str
    quantity: float
    unit: str
    arrival: date
    buyer_id: str
    kind: str = "regular"

    def in_transit(self, today: date) -> bool:
        return self.day <= today < self.arrival


@dataclass
class Recurrence:
    supplier_id: str
    buyer_id: str | None
    orders_6m: int = 0
    orders_12m: int = 0
    consecutive: int = 0                  # meses seguidos con pedido, hasta este mes (o el anterior)
    last_order: Order | None = None
    in_transit: list[Order] = field(default_factory=list)   # por fecha de llegada

    @property
    def recurrent(self) -> bool:
        return self.orders_6m >= RECURRENT_MIN

    @property
    def next_arrival(self) -> Order | None:
        """El pedido en tránsito que llega antes."""
        return self.in_transit[0] if self.in_transit else None

    @property
    def transit_quantity(self) -> float:
        return sum(o.quantity for o in self.in_transit)


def _num(s: str) -> float:
    v = float(s)
    return int(v) if v.is_integer() else v


@lru_cache(maxsize=4)
def load_history(path: Path = HISTORY_PATH) -> tuple[Order, ...]:
    """Los pedidos del CSV (vacío si no existe: el panel y el bot funcionan sin historial)."""
    if not Path(path).exists():
        return ()
    with open(path, encoding="utf-8", newline="") as f:
        rows = csv.DictReader(line for line in f if not line.startswith("#"))
        return tuple(Order(r["order_id"], date.fromisoformat(r["order_date"]), r["supplier_id"], r["material"],
                           _num(r["quantity"]), r["unit"], date.fromisoformat(r["expected_arrival"]),
                           r["buyer_id"], r["kind"]) for r in rows)


def months_back(today: date, n: int) -> date:
    """El mismo día n meses antes (el último del mes si no existe: 31 -> 30)."""
    y, m = divmod(today.year * 12 + today.month - 1 - n, 12)
    return date(y, m + 1, min(today.day, calendar.monthrange(y, m + 1)[1]))


def _consecutive(orders: list[Order], today: date) -> int:
    months = {(o.day.year, o.day.month) for o in orders if o.day <= today}
    y, m = today.year, today.month
    if (y, m) not in months:                 # el pedido de este mes aún puede no haberse hecho
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    n = 0
    while (y, m) in months:
        n += 1
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return n


def recurrence(supplier_id: str, today: date | None = None, buyer_id: str | None = None,
               orders: tuple[Order, ...] | list[Order] | None = None) -> Recurrence:
    """Recurrencia de un proveedor (de todos los compradores, o solo de buyer_id)."""
    today = today or date.today()
    orders = load_history() if orders is None else orders
    mine = [o for o in orders if o.supplier_id == supplier_id and (buyer_id is None or o.buyer_id == buyer_id)
            and o.day <= today]
    r = Recurrence(supplier_id, buyer_id)
    if not mine:
        return r
    r.orders_6m = sum(o.day > months_back(today, 6) for o in mine)
    r.orders_12m = sum(o.day > months_back(today, 12) for o in mine)
    r.consecutive = _consecutive(mine, today)
    r.last_order = max(mine, key=lambda o: (o.day, o.id))
    r.in_transit = sorted((o for o in mine if o.in_transit(today)), key=lambda o: (o.arrival, o.id))
    return r


def by_buyer(buyer_id: str, today: date | None = None,
             orders: tuple[Order, ...] | list[Order] | None = None) -> list[Recurrence]:
    """Todos los proveedores a los que ha pedido un comprador, de más a menos pedidos."""
    orders = load_history() if orders is None else orders
    ids = sorted({o.supplier_id for o in orders if o.buyer_id == buyer_id})
    out = [recurrence(s, today, buyer_id, orders) for s in ids]
    return sorted(out, key=lambda r: (-r.orders_12m, r.supplier_id))


def recurrent_suppliers(buyer_id: str, today: date | None = None,
                        orders: tuple[Order, ...] | list[Order] | None = None) -> list[str]:
    """Los proveedores habituales de un comprador (sus suscripciones automáticas)."""
    return [r.supplier_id for r in by_buyer(buyer_id, today, orders) if r.recurrent]


def buyers_of(supplier_id: str, today: date | None = None,
              orders: tuple[Order, ...] | list[Order] | None = None) -> list[str]:
    """Los compradores para los que un proveedor es habitual."""
    orders = load_history() if orders is None else orders
    ids = sorted({o.buyer_id for o in orders if o.supplier_id == supplier_id})
    return [b for b in ids if recurrence(supplier_id, today, b, orders).recurrent]
