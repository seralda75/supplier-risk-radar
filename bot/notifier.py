"""Notificador: cuando se crea una alerta, avisa a los compradores que siguen a los proveedores afectados.

- Destinatarios: por cada proveedor afectado, los chats suscritos (core/subscriptions): de forma automática,
  los compradores para los que es proveedor habitual (≥3 pedidos en 6 meses); a mano, quien lo siga.
- Urgente: se envía al momento con el evento, la recurrencia, el pedido en tránsito, el margen, los
  medicamentos afectados y el plan, y cuatro botones: Aprobar plan, Falsa alarma, Recordarme mañana y Ver en
  el panel. No urgente: queda pendiente para /resumen.
- Un aviso por chat y alerta (tabla notifications): no se repite aunque se vuelva a procesar la noticia.
- Sin datos sensibles innecesarios: ni gasto, ni cuota, ni puntuación de calidad, ni texto completo de la noticia.

Canales: Channel es la interfaz (send_alert). TelegramChannel la implementa con la Bot API por HTTPS;
añadir WhatsApp o Teams es escribir otra clase (WhatsAppChannel queda como esqueleto documentado).
Si no hay token o no hay internet, no se envía nada, el aviso queda con estado «error» (se reintenta en la
siguiente alerta) y el panel sigue funcionando igual.
"""
from __future__ import annotations

import html
import sqlite3
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date

import requests

from core import subscriptions as subs
from core.countdown import Countdown
from core.labels import product_es, short_supplier
from core.recurrence import habitual_label, recurrence, transit_label
from core.suppliers import load_suppliers
from ui.data import EVENT_SHORT, Alert, build_alerts, duration_es, signed

from . import config

MARGIN_ES = {"rotura_prevista": "rotura prevista", "riesgo_latente": "riesgo latente",
             "margen_ajustado": "margen ajustado", "cubierto": "cubierto", "sin_inventario": "sin stock de reserva"}


def e(text) -> str:
    return html.escape(str(text), quote=False)


# ---------------------------------------------------------------------------
# Canales
# ---------------------------------------------------------------------------

@dataclass
class Button:
    label: str
    data: str = ""              # botón de respuesta (lo atiende bot/telegram_bot.py)
    url: str = ""               # o enlace


@dataclass
class AlertMessage:
    text: str                                   # HTML de Telegram (texto ya escapado)
    buttons: list[list[Button]] = field(default_factory=list)
    link: str = ""                              # el enlace al panel, por si el canal no admite el botón


class ChannelError(Exception):
    pass


class Channel(ABC):
    """Un canal de mensajería. Para añadir uno (Teams, WhatsApp…), implementa estos dos métodos."""
    name = "canal"

    @abstractmethod
    def available(self) -> bool:
        """¿Está configurado? (sin credenciales no se intenta enviar)."""

    @abstractmethod
    def send_alert(self, chat_id: int, message: AlertMessage) -> int | str:
        """Envía el aviso y devuelve el id del mensaje. Lanza ChannelError si no se puede."""


class TelegramChannel(Channel):
    """Bot API de Telegram por HTTPS (requests), sin depender del proceso del bot: el panel puede enviar
    aunque el bot esté parado; las respuestas a los botones las recoge el bot cuando arranque."""
    name = "Telegram"
    TIMEOUT_S = 6

    def __init__(self, token: str | None = None):
        self._token = config.token() if token is None else token

    def available(self) -> bool:
        return bool(self._token)

    def _call(self, method: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        try:
            r = requests.post(f"https://api.telegram.org/bot{self._token}/{method}", json=payload or {},
                              timeout=timeout or self.TIMEOUT_S)
            data = r.json()
        except (requests.RequestException, ValueError) as ex:
            raise ChannelError(config.redact(f"sin conexión con Telegram: {type(ex).__name__}")) from None
        if not data.get("ok"):
            raise ChannelError(config.redact(data.get("description", "error de Telegram")))
        return data["result"]

    def bot_name(self, timeout: float = 3) -> str:
        return self._call("getMe", timeout=timeout).get("username", "")

    @staticmethod
    def _markup(buttons: list[list[Button]], with_urls: bool) -> dict:
        rows = [[({"text": b.label, "url": b.url} if b.url else {"text": b.label, "callback_data": b.data})
                 for b in row if with_urls or not b.url] for row in buttons]
        return {"inline_keyboard": [r for r in rows if r]}

    def send_alert(self, chat_id: int, message: AlertMessage) -> int:
        if not self.available():
            raise ChannelError("Telegram desactivado: falta TELEGRAM_BOT_TOKEN en .env")
        payload = {"chat_id": chat_id, "text": message.text, "parse_mode": "HTML",
                   "link_preview_options": {"is_disabled": True},
                   "reply_markup": self._markup(message.buttons, with_urls=True)}
        try:
            return self._call("sendMessage", payload)["message_id"]
        except ChannelError as ex:
            # Telegram no acepta enlaces a localhost en los botones: el enlace va entonces en el texto
            if "url" not in str(ex).lower() or not message.link:
                raise
        payload["text"] = message.text + f"\n\n📄 Ver en el panel: {e(message.link)}"
        payload["reply_markup"] = self._markup(message.buttons, with_urls=False)
        return self._call("sendMessage", payload)["message_id"]


class WhatsAppChannel(Channel):
    """Esqueleto, sin implementar: WhatsApp Business Cloud API (Meta).

    Para implementarlo:
    - Cuenta de Meta Business verificada, número de WhatsApp Business y token de acceso
      (WHATSAPP_TOKEN y WHATSAPP_PHONE_ID en .env).
    - Fuera de la ventana de 24 h desde el último mensaje del comprador, solo se pueden enviar plantillas
      aprobadas por Meta: la alerta urgente sería una plantilla con variables (proveedor, evento, margen…).
    - Botones: «quick reply» (hasta 3) en la plantilla; sus respuestas llegan por un webhook HTTPS público,
      que tendría que llamar a lo mismo que los botones de Telegram (core/feedback, core/tasks).
    - Envío: POST https://graph.facebook.com/<versión>/<PHONE_ID>/messages; coste por conversación.
    El destinatario sería el teléfono del comprador en lugar del chat_id (otra columna en buyers).
    """
    name = "WhatsApp"

    def available(self) -> bool:
        return False

    def send_alert(self, chat_id: int, message: AlertMessage) -> int | str:
        raise NotImplementedError("WhatsAppChannel es un esqueleto: ver el docstring")


# ---------------------------------------------------------------------------
# Mensajes
# ---------------------------------------------------------------------------

def _recurrence_line(sid: str, buyer_id: str | None, today: date) -> tuple[str, str]:
    """(recurrencia, pedido en tránsito) de un proveedor para un comprador."""
    r = recurrence(sid, today, buyer_id)
    label = habitual_label(r)
    if r.recurrent:
        rec = f"{label} en 12 meses ({r.consecutive} meses seguidos)"
    else:                                   # lo sigue a mano
        rec = f"Lo sigues · {label[0].lower()}{label[1:]}"
    return rec, transit_label(r)


def _margin(c: Countdown) -> str:
    if c.inventory_days is None:
        return f"sin stock de reserva · {c.ttr_days} días de interrupción"
    return f"{signed(c.margin_days)} días · {MARGIN_ES.get(c.status, c.status)}"


def _focus(a: Alert, sids: list[str]) -> Countdown:
    """La cuenta atrás más comprometida entre los proveedores que sigue el chat."""
    cds = [c for c in [a.worst] + a.others if c.supplier_id in sids]
    return min(cds, key=lambda c: (c.margin_days, c.supplier_id)) if cds else a.worst


def callback(kind: str, is_demo: bool, split: str, news_id: str) -> str:
    """Datos del botón (máx. 64 bytes): «ap|d|test|N008». d = demo.db, p = app.db."""
    return f"{kind}|{'d' if is_demo else 'p'}|{split}|{news_id}"


def alert_message(a: Alert, sids: list[str], buyer_id: str | None, split: str, is_demo: bool,
                  today: date | None = None) -> AlertMessage:
    """El aviso urgente para un chat, centrado en sus proveedores afectados."""
    from core.actions import plan_steps
    today = today or date.today()
    sup = load_suppliers()
    c = _focus(a, sids)
    s = sup[c.supplier_id]
    ev = EVENT_SHORT.get(a.r["event_type"], a.r["event_type"])
    dur = duration_es(a.r.get("recovery_reported", ""))
    rec, transit = _recurrence_line(s.id, buyer_id, today)
    meds = ", ".join(product_es(p) for p in c.products) or "ninguno registrado"
    steps = plan_steps(c, s, urgent=True)
    others = [short_supplier(sup[x].name) for x in sids if x != s.id]
    lines = [f"🔴 <b>URGENTE · {e(short_supplier(s.name))}</b> ({s.id})",
             f"<i>{e(a.r['headline'])}</i>",
             "",
             f"<b>Evento:</b> {e(ev)}{' · ' + e(dur) if dur else ''}",
             f"<b>Recurrencia:</b> {e(rec)}",
             f"<b>Pedido en tránsito:</b> {e(transit)}",
             f"<b>Margen:</b> {e(_margin(c))}",
             f"<b>Medicamentos afectados:</b> {e(meds)}"]
    if others:
        lines.append(f"<b>También sigues a:</b> {e(', '.join(others))}")
    lines += ["", "<b>Plan</b>"] + [f"{i}. {e(x.text)} <i>({e(x.owner)} · {e(x.when)})</i>"
                                     for i, x in enumerate(steps, 1)]
    link = config.panel_link(a.id, is_demo)
    buttons = [[Button("✅ Aprobar plan", callback("ap", is_demo, split, a.id)),
                Button("❌ Falsa alarma", callback("fa", is_demo, split, a.id))],
               [Button("⏰ Recordarme mañana", callback("rm", is_demo, split, a.id)),
                Button("📄 Ver en el panel", url=link)]]
    return AlertMessage("\n".join(lines), buttons, link)


def summary_line(a: Alert, sids: list[str]) -> str:
    """Una línea para /resumen (HTML ya escapado)."""
    c = _focus(a, sids)
    s = load_suppliers()[c.supplier_id]
    ev = EVENT_SHORT.get(a.r["event_type"], a.r["event_type"])
    return (f"<b>{e(short_supplier(s.name))}</b> · {e(ev)} · margen {e(_margin(c))}\n"
            f"  <i>{e(a.r['headline'])}</i>")


# ---------------------------------------------------------------------------
# Notificar
# ---------------------------------------------------------------------------

@dataclass
class Report:
    urgent: bool
    chats: list[int] = field(default_factory=list)      # chats con aviso nuevo
    channel_ok: bool = True
    thread: threading.Thread | None = None

    def text(self) -> str:
        n = len(self.chats)
        if not n:
            return "sin compradores suscritos a estos proveedores"
        who = f"{n} comprador{'es' if n > 1 else ''}"
        if not self.urgent:
            return f"queda para el /resumen semanal de {who}"
        return f"aviso a {who} por Telegram" if self.channel_ok else "Telegram desactivado: no se ha enviado"


def recipients(a: Alert, con: sqlite3.Connection, today: date | None = None) -> dict[int, list[str]]:
    """{chat_id: [proveedores afectados que sigue]}."""
    out: dict[int, list[str]] = {}
    for c in [a.worst] + a.others:
        for chat in subs.subscribers(c.supplier_id, today, con):
            out.setdefault(chat, []).append(c.supplier_id)
    return out


def notify(a: Alert, split: str, is_demo: bool, con: sqlite3.Connection, channel: Channel | None = None,
           today: date | None = None, background: bool = True) -> Report:
    """Avisa de una alerta recién creada. Las reservas (sin duplicados) se hacen aquí; el envío, en un hilo
    aparte si background=True, para no frenar el panel si Telegram tarda o no hay internet."""
    channel = channel or TelegramChannel()
    urgent = bool(a.r.get("urgent"))
    rep = Report(urgent, channel_ok=channel.available())
    todo: list[tuple[int, int, AlertMessage]] = []
    for chat, sids in recipients(a, con, today).items():
        b = subs.buyer(chat, con)
        kind = "urgente" if urgent else "resumen"
        nid = subs.claim(chat, split, a.id, kind, sids, summary_line(a, sids), con)
        if nid is None:
            continue                                   # ya avisado
        rep.chats.append(chat)
        if urgent:
            todo.append((nid, chat, alert_message(a, sids, b["buyer_id"] if b else None, split, is_demo, today)))

    def send() -> None:
        for nid, chat, msg in todo:
            try:
                mid = channel.send_alert(chat, msg)
                subs.mark(nid, "enviado", int(mid) if str(mid).isdigit() else None, con=con)
            except Exception as ex:                    # sin token, sin internet, chat bloqueado…
                subs.mark(nid, "error", error=config.redact(str(ex)), con=con)

    if todo:
        if background:
            rep.thread = threading.Thread(target=send, name="notify", daemon=True)
            rep.thread.start()
        else:
            send()
    return rep


def notify_result(result: dict, split: str, is_demo: bool, con: sqlite3.Connection,
                  channel: Channel | None = None, today: date | None = None, background: bool = True) -> Report | None:
    """Lo mismo a partir de un resultado del pipeline (assess(...).model_dump()). None si no es una alerta."""
    alerts = build_alerts([result])
    return notify(alerts[0], split, is_demo, con, channel, today, background) if alerts else None


def status(timeout: float = 3) -> tuple[bool, str]:
    """(activo, texto) para el panel: «Telegram activo · @bot» o «Telegram desactivado (…)»."""
    ch = TelegramChannel()
    if not ch.available():
        return False, "Telegram desactivado (sin token)"
    try:
        name = ch.bot_name(timeout)
    except ChannelError:
        return False, "Telegram desactivado (sin conexión)"
    return True, f"Telegram activo · @{name}"
