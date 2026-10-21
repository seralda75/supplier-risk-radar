"""Acciones en curso de cada alerta: pedidos, recordatorios y comunicaciones (SQLite).

Los pedidos no se envían a ningún sitio: quedan como «Pedido pendiente de envío al ERP», listos para que
una integración (SAP, Oracle…) los recoja. La propuesta del pedido (proveedor, cantidad, fecha y
prioridad) sale de la cuenta atrás y del mismo plan que se recomienda en el panel (actions.situation).
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from .actions import situation
from .countdown import Countdown
from .feedback import _LOCK, _db
from .suppliers import Supplier, load_suppliers

if TYPE_CHECKING:
    from .order_calendar import MaterialPlan

ORDER_STATES = {"pendiente_erp": "Pedido pendiente de envío al ERP", "hecho": "Hecho"}
REMINDER_STATES = {"pendiente": "Pendiente", "hecho": "Hecho"}
COMM_KINDS = {"correo": "Correo al proveedor", "nota": "Nota interna"}
PRIORITIES = ["Alta", "Media", "Baja"]
UNIT_ES = {"kg": "kg", "units": "unidades", "m2": "m²", "litres": "litros"}
OTHER_SUPPLIER = "otro"        # proveedor sin ID: no aprobado o servicio puntual (cualificación de urgencia)


def ensure(con: sqlite3.Connection) -> sqlite3.Connection:
    """Crea las tablas de pedidos y recordatorios si no existen."""
    with _LOCK, con:
        con.execute("""CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY, ts TEXT, split TEXT, news_id TEXT, supplier_id TEXT, supplier_name TEXT,
            material TEXT, quantity REAL, unit TEXT, needed_by TEXT, priority TEXT, calc TEXT,
            status TEXT, user TEXT, done_ts TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY, ts TEXT, split TEXT, news_id TEXT, text TEXT, owner TEXT, due TEXT,
            status TEXT, user TEXT, done_ts TEXT)""")
        # Comunicaciones marcadas como enviadas (correo al proveedor, nota interna). No se envían de verdad.
        con.execute("""CREATE TABLE IF NOT EXISTS communications (
            id INTEGER PRIMARY KEY, ts TEXT, split TEXT, news_id TEXT, kind TEXT, recipient TEXT,
            subject TEXT, body TEXT, source TEXT, user TEXT)""")
    return con


def _con(con: sqlite3.Connection | None) -> sqlite3.Connection:
    return ensure(_db(con))


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Propuesta de pedido
# ---------------------------------------------------------------------------

@dataclass
class OrderDraft:
    supplier_id: str              # ID o OTHER_SUPPLIER
    supplier_name: str
    material: str
    quantity: float
    unit: str
    needed_by: date
    priority: str
    calc: str                     # cómo se ha calculado la cantidad, en una frase
    options: list[tuple[str, str]]  # proveedores entre los que elegir: (id, nombre)


def monthly_need(text: str) -> tuple[float | None, str]:
    """'3500 kg' -> (3500.0, 'kg'); '2400000 units' -> (2400000.0, 'unidades'); '' -> (None, '')."""
    m = re.match(r"\s*([\d.,]+)\s*(\S+)?", text or "")
    if not m:
        return None, ""
    value = float(m.group(1).replace(",", ""))
    return value, UNIT_ES.get(m.group(2) or "", m.group(2) or "")


def _fmt(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".")


def suggest_order(c: Countdown, s: Supplier, level: str, today: date | None = None) -> OrderDraft:
    """Pedido propuesto para el proveedor más comprometido de una alerta.

    - Proveedor: el alternativo si llega antes de que se acabe el stock; si no, el que propone el plan
      (el alternativo con envío urgente, el mismo proveedor con una asignación parcial u otro por cualificar).
    - Cantidad: necesidad mensual × días de déficit / 30, donde los días de déficit son los que el stock
      no cubre hasta que el proveedor se recupera (recuperación − stock).
    - Fecha requerida: el día en que se acaba el stock (hoy si no hay stock de reserva).
    - Prioridad: alta si es crítica o el margen es negativo; media si hay que vigilarla; baja en el resto.
    """
    today = today or date.today()
    sup = load_suppliers()
    alt = sup.get(s.alternate_id) if s.alternate_id else None
    case = situation(c, s)
    options = [(s.id, s.name)] + ([(alt.id, alt.name)] if alt else [])
    other = (OTHER_SUPPLIER, {"sin_stock_alt_afectado": "Servicio puntual fuera de la zona afectada",
                              "sin_stock_unico": "Sustituto puntual (por cualificar)"}.get(
        case, "Proveedor no aprobado (cualificación de urgencia)"))
    options.append(other)
    if alt and case in ("alt_a_tiempo", "alt_insuficiente", "alt_tarde", "sin_stock_alt"):
        pick = (alt.id, alt.name)
    elif case in ("sin_stock_unico", "sin_stock_alt_afectado"):
        pick = other
    else:                     # cubre, sin_corte, unico_deficit, alt_afectado: el plan habla con el mismo proveedor
        pick = (s.id, s.name)

    need, unit = monthly_need(c.monthly_requirement or s.monthly_requirement)
    if c.inventory_days is None:                     # logística y servicios: días de servicio
        days = float(c.ttr_days)
        qty, unit = days, "días de servicio"
        calc = f"Sin stock de reserva: contratar el servicio los {c.ttr_days} días que dura la interrupción."
    else:
        days = max(0.0, c.ttr_days - c.inventory_days)
        if need is None:
            qty, unit = 0.0, unit or "unidades"
            calc = "Sin necesidad mensual registrada para este material: indica la cantidad."
        elif days == 0:
            qty = 0.0
            calc = (f"Sin déficit: el stock ({c.inventory_days:.0f} d) cubre la recuperación ({c.ttr_days} d). "
                    "El pedido es opcional.")
        else:
            qty = round(need * days / 30)
            calc = (f"{_fmt(need)} {unit}/mes × {days:.0f} días de déficit / 30 = {_fmt(qty)} {unit} "
                    f"(déficit = {c.ttr_days} d hasta que se recupera el proveedor − {c.inventory_days:.0f} d de stock)")
    needed_by = today + timedelta(days=int(c.tts_days)) if c.inventory_days is not None else today
    priority = "Alta" if level == "critica" or c.margin_days < 0 else ("Media" if level == "vigilar" else "Baja")
    return OrderDraft(pick[0], pick[1], s.material, qty, unit, needed_by, priority, calc, options)


def suggest_restock(mp: "MaterialPlan", today: date | None = None) -> OrderDraft:
    """Pedido propuesto desde el calendario para un material (core/order_calendar.MaterialPlan).

    - Proveedor: el que se usaría (el alternativo si el principal está afectado).
    - Cantidad: con rotura prevista, necesidad mensual × días de déficit / 30 (los días entre la rotura y la
      recuperación del proveedor, como en la ventana de la alerta); si no, un mes de necesidad.
    - Fecha requerida: el día en que se acaba el stock.
    - Prioridad: alta si hay rotura prevista o la fecha límite para pedir ya ha pasado; media en peligro.
    """
    today = today or date.today()
    sup = load_suppliers()
    m = mp.material
    options = [(m.primary_id, sup[m.primary_id].name)]
    if m.alternate_id:
        options.append((m.alternate_id, sup[m.alternate_id].name))
    options.append((OTHER_SUPPLIER, "Proveedor no aprobado (cualificación de urgencia)"))
    need, unit = monthly_need(m.monthly)
    if need is None:
        qty, calc = 0.0, "Sin necesidad mensual registrada para este material: indica la cantidad."
    elif mp.stockout and mp.recovery and mp.recovery > mp.stockout:
        days = (mp.recovery - mp.stockout).days
        qty = round(need * days / 30)
        calc = (f"{_fmt(need)} {unit}/mes × {days} días de déficit / 30 = {_fmt(qty)} {unit} (déficit = días entre la "
                "rotura prevista y la recuperación del proveedor)")
    else:
        qty, calc = need, f"Reposición: un mes de necesidad ({_fmt(need)} {unit}/mes)."
    priority = ("Alta" if mp.status == "rotura" or mp.days_left < 0 else
                "Media" if mp.status == "peligro" else "Baja")
    needed_by = today + timedelta(days=int(mp.stock_days))
    return OrderDraft(mp.supplier_id, sup[mp.supplier_id].name, m.name, qty, unit, needed_by, priority, calc, options)


# ---------------------------------------------------------------------------
# Guardar, listar y cerrar
# ---------------------------------------------------------------------------

def create_order(split: str, news_id: str, supplier_id: str, supplier_name: str, material: str, quantity: float,
                 unit: str, needed_by: date, priority: str, calc: str = "", user: str = "comprador",
                 con: sqlite3.Connection | None = None) -> int:
    if quantity <= 0:
        raise ValueError("La cantidad debe ser mayor que 0")
    if priority not in PRIORITIES:
        raise ValueError(f"Prioridad desconocida: {priority}")
    db = _con(con)
    with _LOCK, db:
        cur = db.execute("INSERT INTO orders (ts, split, news_id, supplier_id, supplier_name, material, quantity, "
                         "unit, needed_by, priority, calc, status, user) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                         (_now(), split, news_id, supplier_id, supplier_name, material, float(quantity), unit,
                          needed_by.isoformat(), priority, calc, "pendiente_erp", user))
    return cur.lastrowid


def create_reminder(split: str, news_id: str, text: str, owner: str, due: date, user: str = "comprador",
                    con: sqlite3.Connection | None = None) -> int:
    if not text.strip():
        raise ValueError("El recordatorio necesita un texto")
    db = _con(con)
    with _LOCK, db:
        cur = db.execute("INSERT INTO reminders (ts, split, news_id, text, owner, due, status, user) "
                         "VALUES (?,?,?,?,?,?,?,?)",
                         (_now(), split, news_id, text.strip(), owner.strip(), due.isoformat(), "pendiente", user))
    return cur.lastrowid


def log_communication(split: str, news_id: str, kind: str, recipient: str, subject: str, body: str,
                      source: str, user: str = "comprador", con: sqlite3.Connection | None = None) -> int:
    """Registra en la auditoría que una comunicación se ha marcado como enviada (kind: correo | nota)."""
    if kind not in COMM_KINDS:
        raise ValueError(f"Comunicación desconocida: {kind}")
    db = _con(con)
    with _LOCK, db:
        cur = db.execute("INSERT INTO communications (ts, split, news_id, kind, recipient, subject, body, source, "
                         "user) VALUES (?,?,?,?,?,?,?,?,?)",
                         (_now(), split, news_id, kind, recipient, subject, body, source, user))
    return cur.lastrowid


def mark_done(kind: str, item_id: int, con: sqlite3.Connection | None = None) -> None:
    table = {"order": "orders", "reminder": "reminders"}[kind]
    db = _con(con)
    with _LOCK, db:
        db.execute(f"UPDATE {table} SET status = 'hecho', done_ts = ? WHERE id = ?", (_now(), int(item_id)))


def items(split: str, con: sqlite3.Connection | None = None) -> list[dict]:
    """Pedidos, recordatorios y comunicaciones de un conjunto, los pendientes primero y por fecha.
    Una comunicación ya está hecha (marcada como enviada)."""
    db = _con(con)
    with _LOCK:
        orders = db.execute("SELECT id, ts, news_id, supplier_id, supplier_name, material, quantity, unit, "
                            "needed_by, priority, calc, status, user, done_ts FROM orders WHERE split = ?",
                            (split,)).fetchall()
        rems = db.execute("SELECT id, ts, news_id, text, owner, due, status, user, done_ts FROM reminders "
                          "WHERE split = ?", (split,)).fetchall()
        comms = db.execute("SELECT id, ts, news_id, kind, recipient, subject, body, source, user FROM "
                           "communications WHERE split = ?", (split,)).fetchall()
    out = [dict(zip(["id", "ts", "news_id", "supplier_id", "supplier_name", "material", "quantity", "unit",
                     "needed_by", "priority", "calc", "status", "user", "done_ts"], r), kind="order", date=r[8])
           for r in orders]
    out += [dict(zip(["id", "ts", "news_id", "text", "owner", "due", "status", "user", "done_ts"], r),
                 kind="reminder", date=r[5]) for r in rems]
    out += [dict(zip(["id", "ts", "news_id", "channel", "recipient", "subject", "body", "source", "user"], r),
                 kind="comm", date=r[1][:10], status="hecho", done_ts=r[1]) for r in comms]
    return sorted(out, key=lambda x: (x["status"] == "hecho", x["date"], x["ts"]))
