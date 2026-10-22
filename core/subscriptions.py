"""Compradores registrados en Telegram, sus suscripciones a proveedores y los avisos enviados (SQLite).

- buyers: cada chat de Telegram registrado y el comprador ficticio que eligió (core/recurrence.BUYERS).
  Varios chats pueden registrarse a la vez, también como el mismo comprador.
- subscriptions: qué proveedores sigue cada chat. «auto»: los proveedores habituales de su comprador
  (recurrencia); «manual»: /seguir. /dejar desactiva la fila (también una automática), sin borrarla, para que
  la sincronización no la vuelva a crear.
- notifications: un aviso por chat y alerta, para no repetirlo. Urgentes: se envían al momento; el resto
  queda pendiente para /resumen.

Las tablas viven en la misma SQLite que el resto del panel: data/app.db o, en modo demo, data/demo.db.
Nada de esto toca la entrega ni los resultados. «Reiniciar demo» vacía suscripciones y avisos de la demo,
pero conserva los chats registrados (las suscripciones automáticas se recrean solas).
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

from rapidfuzz import fuzz, process

from .feedback import _LOCK, _db
from .matching import normalize
from .recurrence import BUYERS, recurrent_suppliers
from .suppliers import Supplier, load_suppliers

NOTIFY_STATES = {"enviando": "Enviando", "enviado": "Enviado", "pendiente": "Pendiente para /resumen", "resumido": "Incluido en /resumen",
                 "error": "No se pudo enviar"}


def ensure(con: sqlite3.Connection) -> sqlite3.Connection:
    with _LOCK, con:
        con.execute("""CREATE TABLE IF NOT EXISTS buyers (
            chat_id INTEGER PRIMARY KEY, buyer_id TEXT, name TEXT, categories TEXT, chat_name TEXT, ts TEXT)""")
        con.execute("""CREATE TABLE IF NOT EXISTS subscriptions (
            chat_id INTEGER, supplier_id TEXT, origin TEXT, active INTEGER, ts TEXT,
            PRIMARY KEY (chat_id, supplier_id))""")
        con.execute("""CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY, ts TEXT, chat_id INTEGER, split TEXT, news_id TEXT, kind TEXT,
            supplier_ids TEXT, status TEXT, line TEXT, message_id INTEGER, error TEXT,
            UNIQUE (chat_id, split, news_id))""")
    return con


def _con(con: sqlite3.Connection | None) -> sqlite3.Connection:
    return ensure(_db(con))


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Compradores
# ---------------------------------------------------------------------------

def register(chat_id: int, buyer_id: str, chat_name: str = "", today: date | None = None,
             con: sqlite3.Connection | None = None) -> None:
    """Registra (o cambia) el comprador de un chat y le suscribe a sus proveedores habituales.
    Si cambia de comprador, se quitan las suscripciones automáticas del anterior (las manuales se quedan)."""
    if buyer_id not in BUYERS:
        raise ValueError(f"Comprador desconocido: {buyer_id}")
    b = BUYERS[buyer_id]
    db = _con(con)
    with _LOCK, db:
        old = db.execute("SELECT buyer_id FROM buyers WHERE chat_id = ?", (chat_id,)).fetchone()
        if old and old[0] != buyer_id:
            db.execute("DELETE FROM subscriptions WHERE chat_id = ? AND origin = 'auto'", (chat_id,))
        db.execute("INSERT OR REPLACE INTO buyers (chat_id, buyer_id, name, categories, chat_name, ts) "
                   "VALUES (?,?,?,?,?,?)", (chat_id, buyer_id, b["name"], "; ".join(b["categories"]), chat_name,
                                            _now()))
    sync_auto(chat_id, today, db)


def buyer(chat_id: int, con: sqlite3.Connection | None = None) -> dict | None:
    db = _con(con)                       # antes del candado: ensure() también lo toma
    with _LOCK:
        r = db.execute("SELECT chat_id, buyer_id, name, categories, chat_name, ts FROM buyers "
                              "WHERE chat_id = ?", (chat_id,)).fetchone()
    return dict(zip(["chat_id", "buyer_id", "name", "categories", "chat_name", "ts"], r)) if r else None


def chats(con: sqlite3.Connection | None = None) -> list[dict]:
    """Todos los chats registrados."""
    db = _con(con)
    with _LOCK:
        rows = db.execute("SELECT chat_id, buyer_id, name, categories, chat_name, ts FROM buyers "
                                 "ORDER BY ts").fetchall()
    return [dict(zip(["chat_id", "buyer_id", "name", "categories", "chat_name", "ts"], r)) for r in rows]


# ---------------------------------------------------------------------------
# Suscripciones
# ---------------------------------------------------------------------------

def sync_auto(chat_id: int, today: date | None = None, con: sqlite3.Connection | None = None) -> None:
    """Suscribe el chat a los proveedores habituales de su comprador. No reactiva los que dejó con /dejar."""
    db = _con(con)
    b = buyer(chat_id, db)
    if not b:
        return
    with _LOCK, db:
        db.executemany("INSERT OR IGNORE INTO subscriptions (chat_id, supplier_id, origin, active, ts) "
                       "VALUES (?,?,'auto',1,?)",
                       [(chat_id, s, _now()) for s in recurrent_suppliers(b["buyer_id"], today)])


def find_suppliers(query: str) -> list[Supplier]:
    """Proveedores que encajan con lo que escribe el comprador: «S015», «Lumina», «lumina glass»…
    Primero el ID exacto; si no, los nombres que contienen el texto; si no, el nombre más parecido."""
    sup = load_suppliers()
    q = query.strip()
    if q.upper() in sup:
        return [sup[q.upper()]]
    norm = normalize(q).strip()
    if not norm:
        return []
    hits = [s for s in sup.values() if norm in normalize(s.name)]
    if hits:
        return hits
    best = process.extractOne(norm, {s.id: normalize(s.name) for s in sup.values()}, scorer=fuzz.partial_ratio,
                              score_cutoff=80)
    return [sup[best[2]]] if best else []


def follow(chat_id: int, supplier_id: str, con: sqlite3.Connection | None = None) -> None:
    db = _con(con)
    with _LOCK, db:
        db.execute("INSERT INTO subscriptions (chat_id, supplier_id, origin, active, ts) VALUES (?,?,'manual',1,?) "
                   "ON CONFLICT (chat_id, supplier_id) DO UPDATE SET active = 1, ts = excluded.ts",
                   (chat_id, supplier_id, _now()))


def unfollow(chat_id: int, supplier_id: str, con: sqlite3.Connection | None = None) -> bool:
    """Deja de seguir un proveedor. Devuelve False si no lo seguía."""
    db = _con(con)
    with _LOCK, db:
        cur = db.execute("UPDATE subscriptions SET active = 0, ts = ? WHERE chat_id = ? AND supplier_id = ? "
                         "AND active = 1", (_now(), chat_id, supplier_id))
    return cur.rowcount > 0


def followed(chat_id: int, con: sqlite3.Connection | None = None) -> list[dict]:
    """Proveedores que sigue un chat: [{supplier_id, origin}] (auto primero)."""
    db = _con(con)
    with _LOCK:
        rows = db.execute("SELECT supplier_id, origin FROM subscriptions WHERE chat_id = ? AND active = 1 "
                                 "ORDER BY origin, supplier_id", (chat_id,)).fetchall()
    return [{"supplier_id": r[0], "origin": r[1]} for r in rows]


def subscribers(supplier_id: str, today: date | None = None, con: sqlite3.Connection | None = None) -> list[int]:
    """Chats suscritos a un proveedor (antes se sincronizan las automáticas: tras «Reiniciar demo» se recrean)."""
    db = _con(con)
    for c in chats(db):
        sync_auto(c["chat_id"], today, db)
    with _LOCK:
        rows = db.execute("SELECT chat_id FROM subscriptions WHERE supplier_id = ? AND active = 1 ORDER BY chat_id",
                          (supplier_id,)).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# Avisos
# ---------------------------------------------------------------------------

def claim(chat_id: int, split: str, news_id: str, kind: str, supplier_ids: list[str], line: str,
          con: sqlite3.Connection | None = None) -> int | None:
    """Reserva el aviso de una alerta para un chat. None si ya se le avisó (no se repite).
    kind: urgente (estado inicial «enviando») | resumen (estado «pendiente»)."""
    db = _con(con)
    with _LOCK, db:
        cur = db.execute("INSERT OR IGNORE INTO notifications (ts, chat_id, split, news_id, kind, supplier_ids, "
                         "status, line) VALUES (?,?,?,?,?,?,?,?)",
                         (_now(), chat_id, split, news_id, kind, "; ".join(supplier_ids),
                          "enviando" if kind == "urgente" else "pendiente", line))
    return cur.lastrowid if cur.rowcount else None


def mark(notification_id: int, status: str, message_id: int | None = None, error: str = "",
         con: sqlite3.Connection | None = None) -> None:
    if status not in NOTIFY_STATES:
        raise ValueError(f"Estado desconocido: {status}")
    db = _con(con)
    with _LOCK, db:
        db.execute("UPDATE notifications SET status = ?, message_id = ?, error = ? WHERE id = ?",
                   (status, message_id, error[:300], notification_id))


def pending_summary(chat_id: int, days: int = 7, con: sqlite3.Connection | None = None) -> list[dict]:
    """Alertas no urgentes de los últimos `days` días para un chat, aún sin enviar en un /resumen."""
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    db = _con(con)
    with _LOCK:
        rows = db.execute("SELECT id, ts, split, news_id, supplier_ids, line FROM notifications "
                                 "WHERE chat_id = ? AND kind = 'resumen' AND status = 'pendiente' AND ts >= ? "
                                 "ORDER BY ts", (chat_id, since)).fetchall()
    return [dict(zip(["id", "ts", "split", "news_id", "supplier_ids", "line"], r)) for r in rows]


def sent(news_id: str | None = None, con: sqlite3.Connection | None = None) -> list[dict]:
    """Avisos registrados (de una alerta o todos), para el panel y los tests."""
    q = "SELECT id, ts, chat_id, split, news_id, kind, supplier_ids, status, error FROM notifications"
    args: tuple = ()
    if news_id:
        q, args = q + " WHERE news_id = ?", (news_id,)
    db = _con(con)
    with _LOCK:
        rows = db.execute(q + " ORDER BY id", args).fetchall()
    return [dict(zip(["id", "ts", "chat_id", "split", "news_id", "kind", "supplier_ids", "status", "error"], r))
            for r in rows]


def reset_demo(con: sqlite3.Connection) -> None:
    """Para «Reiniciar demo»: borra suscripciones y avisos, pero no los chats registrados."""
    ensure(con)
    with _LOCK, con:
        con.execute("DELETE FROM subscriptions")
        con.execute("DELETE FROM notifications")
