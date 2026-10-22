"""Notificador (bot/notifier.py) y botones de los avisos (bot/telegram_bot.py), con un canal falso: sin red."""
import asyncio
from datetime import date, timedelta
from types import SimpleNamespace

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot import notifier
from bot import telegram_bot as tb
from core import demo, feedback, results, subscriptions as subs, tasks
from core.recurrence import load_history
from ui.data import build_alerts

REF = max(o.day for o in load_history())         # día de referencia del historial sintético


class FakeChannel(notifier.Channel):
    name = "falso"

    def __init__(self, ok=True):
        self.ok, self.sent = ok, []

    def available(self):
        return self.ok

    def send_alert(self, chat_id, message):
        self.sent.append((chat_id, message))
        return 1000 + len(self.sent)


def alert(news_id, split="validation"):
    r = demo.precomputed(news_id) if split == "validation" else next(
        x for x in results.load(split)["results"] if x["news_id"] == news_id)
    return build_alerts([r])[0]


def test_urgente_avisa_al_momento_a_los_compradores_habituales(tmp_path):
    con = demo.connect(tmp_path / "demo.db")
    subs.register(111, "B1", "", REF, con)        # APIs y excipientes: Nordic Lipids es habitual
    subs.register(222, "B2", "", REF, con)        # envases: no
    a = alert("N008")                             # Nordic Lipids: duda sobre la continuidad (urgente)
    ch = FakeChannel()
    rep = notifier.notify(a, "test", True, con, ch, REF, background=False)
    assert rep.urgent and rep.chats == [111] and "1 comprador por Telegram" in rep.text()
    (chat, msg), = ch.sent
    t = msg.text
    assert chat == 111 and t.startswith("🔴 <b>URGENTE · Nordic Lipids</b> (S012)")
    for part in ("<b>Evento:</b>", "<b>Recurrencia:</b> Proveedor habitual · 12 pedidos", "<b>Pedido en tránsito:</b>",
                 "<b>Margen:</b>", "<b>Medicamentos afectados:</b> vacuna HX-RSV (ARNm)", "<b>Plan</b>\n1. "):
        assert part in t, part
    assert "llega el" in t                        # 90 días de plazo: hay pedidos en camino
    assert "€" not in t and "EUR" not in t        # sin gasto ni otros datos sensibles
    labels = [b.label for row in msg.buttons for b in row]
    assert labels == ["✅ Aprobar plan", "❌ Falsa alarma", "⏰ Recordarme mañana", "📄 Ver en el panel"]
    assert msg.buttons[0][0].data == "ap|d|test|N008" and len(msg.buttons[0][0].data.encode()) <= 64
    assert msg.buttons[1][1].url == "http://localhost:8501/?demo=1&alert=N008"
    assert subs.sent("N008", con)[0]["status"] == "enviado"
    # no se repite
    assert notifier.notify(a, "test", True, con, ch, REF, background=False).chats == []
    assert len(ch.sent) == 1


def test_una_alerta_de_dos_proveedores_llega_a_cada_comprador_con_lo_suyo(tmp_path):
    con = demo.connect(tmp_path / "demo.db")
    subs.register(111, "B1", "", REF, con)
    subs.register(222, "B2", "", REF, con)
    ch = FakeChannel()
    notifier.notify(alert("N044"), "test", True, con, ch, REF, background=False)   # Taizhou (B1) y Zhejiang (B2)
    by_chat = {c: m.text for c, m in ch.sent}
    assert "Taizhou" in by_chat[111].splitlines()[0] and "Zhejiang" in by_chat[222].splitlines()[0]


def test_no_urgente_queda_para_el_resumen(tmp_path):
    con = demo.connect(tmp_path / "demo.db")
    subs.register(333, "B3", "", REF, con)
    ch = FakeChannel()
    rep = notifier.notify(alert("N051"), "test", True, con, ch, REF, background=False)   # Atlas (B3), no urgente
    assert ch.sent == [] and rep.chats == [333] and "resumen" in rep.text()
    (p,) = subs.pending_summary(333, con=con)
    assert p["news_id"] == "N051" and "Atlas Cleanroom Garments" in p["line"]


def test_seguir_a_mano_un_proveedor_no_habitual_tambien_avisa(tmp_path):
    con = demo.connect(tmp_path / "demo.db")
    subs.register(333, "B3", "", REF, con)
    subs.follow(333, "S012", con)
    ch = FakeChannel()
    notifier.notify(alert("N008"), "test", True, con, ch, REF, background=False)
    assert ch.sent[0][0] == 333 and "Lo sigues · sin pedidos" in ch.sent[0][1].text


def test_sin_token_no_envia_y_se_reintenta_despues(tmp_path):
    con = demo.connect(tmp_path / "demo.db")
    subs.register(111, "B1", "", REF, con)
    a = alert("N008")
    rep = notifier.notify(a, "test", True, con, notifier.TelegramChannel(token=""), REF, background=False)
    assert rep.text() == "Telegram desactivado: no se ha enviado"
    n = subs.sent("N008", con)[0]
    assert n["status"] == "error" and "TELEGRAM_BOT_TOKEN" in n["error"]
    ch = FakeChannel()
    notifier.notify(a, "test", True, con, ch, REF, background=False)
    assert len(ch.sent) == 1 and subs.sent("N008", con)[0]["status"] == "enviado"


def test_el_texto_se_escapa(tmp_path):
    con = demo.connect(tmp_path / "demo.db")
    subs.register(111, "B1", "", REF, con)
    a = alert("N008")
    a.r = dict(a.r, headline="Nordic <script> & \"Lipids\"")
    ch = FakeChannel()
    notifier.notify(a, "test", True, con, ch, REF, background=False)
    assert "<i>Nordic &lt;script&gt; &amp; \"Lipids\"</i>" in ch.sent[0][1].text


def test_telegram_sin_enlace_a_localhost_en_el_boton_lo_pone_en_el_texto(monkeypatch):
    ch = notifier.TelegramChannel(token="123:X")
    calls = []

    def fake_call(method, payload=None, timeout=None):
        calls.append(payload)
        if len(calls) == 1:
            raise notifier.ChannelError("Bad Request: inline keyboard button URL 'http://localhost:8501' is invalid")
        return {"message_id": 7}
    monkeypatch.setattr(ch, "_call", fake_call)
    msg = notifier.AlertMessage("hola", [[notifier.Button("A", "ap|d|test|N1"),
                                          notifier.Button("Ver", url="http://localhost:8501/?alert=N1")]],
                                "http://localhost:8501/?alert=N1")
    assert ch.send_alert(5, msg) == 7
    assert calls[1]["reply_markup"] == {"inline_keyboard": [[{"text": "A", "callback_data": "ap|d|test|N1"}]]}
    assert calls[1]["text"].endswith("Ver en el panel: http://localhost:8501/?alert=N1")
    assert calls[0]["parse_mode"] == "HTML"


def test_whatsapp_es_un_esqueleto():
    w = notifier.WhatsAppChannel()
    assert not w.available() and "plantillas" in notifier.WhatsAppChannel.__doc__


# ---------------------------------------------------------------------------
# Botones del aviso en el bot: se guardan en la misma SQLite y el panel los ve
# ---------------------------------------------------------------------------

class Query:
    def __init__(self, data, markup):
        self.data, self.answered, self.markups = data, [], []
        self.message = SimpleNamespace(reply_markup=markup)

    async def answer(self, text=None, **kw):
        self.answered.append(text)

    async def edit_message_reply_markup(self, markup=None, **kw):
        self.markups.append(markup)


def press(con, data):
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Aprobar plan", callback_data="ap|d|test|N008"),
         InlineKeyboardButton("❌ Falsa alarma", callback_data="fa|d|test|N008")],
        [InlineKeyboardButton("⏰ Recordarme mañana", callback_data="rm|d|test|N008"),
         InlineKeyboardButton("📄 Ver en el panel", url="http://localhost:8501/?demo=1&alert=N008")]])
    q = Query(data, markup)
    upd = SimpleNamespace(callback_query=q, effective_chat=SimpleNamespace(id=111, full_name="x", title=None))
    ctx = SimpleNamespace(bot_data={"demo": True, "con": con, "cons": {True: con}}, args=[])
    asyncio.run(tb.on_alert_button(upd, ctx))
    return q


def test_aprobar_plan_desde_telegram(tmp_path):
    con = demo.connect(tmp_path / "demo.db")
    subs.register(111, "B1", "", REF, con)
    q = press(con, "ap|d|test|N008")
    v = feedback.active("test", con)["N008"]
    assert (v["verdict"], v["user"], v["channel"]) == ("plan_aprobado", "Lucía Herrera", "telegram")
    rows = q.markups[0].inline_keyboard
    assert rows[0][0].text == "✅ Plan aprobado · Lucía Herrera" and rows[1][1].url   # el enlace se queda


def test_falsa_alarma_desde_telegram(tmp_path):
    con = demo.connect(tmp_path / "demo.db")
    subs.register(111, "B1", "", REF, con)
    press(con, "fa|d|test|N008")
    assert feedback.active("test", con)["N008"]["verdict"] == "falsa_alarma"


def test_recordarme_manana_crea_un_recordatorio_y_el_bot_lo_envia_ese_dia(tmp_path):
    con = demo.connect(tmp_path / "demo.db")
    subs.register(111, "B1", "", REF, con)
    subs.claim(111, "test", "N008", "urgente", ["S012"], "", con)
    q = press(con, "rm|d|test|N008")
    (r,) = [x for x in tasks.items("test", con) if x["kind"] == "reminder"]
    assert r["due"] == (date.today() + timedelta(days=1)).isoformat() and "Nordic Lipids" in r["text"]
    assert r["owner"] == "Lucía Herrera" and q.markups[0].inline_keyboard[1][0].text == "⏰ Recordatorio creado"
    # el día que vence, el bot lo envía una sola vez
    con.execute("UPDATE reminders SET due = ?", (date.today().isoformat(),))
    sent = []

    async def send_message(chat_id, text, **kw):
        sent.append((chat_id, text))
        return SimpleNamespace(message_id=1)
    app = SimpleNamespace(bot_data={"cons": {True: con}}, bot=SimpleNamespace(send_message=send_message))
    assert asyncio.run(tb.remind_due(app)) == 1 and asyncio.run(tb.remind_due(app)) == 0
    assert sent[0][0] == 111 and "Recordatorio" in sent[0][1]


def test_ajuste_urgentes_en_el_resumen_no_avisa_al_momento(tmp_path):
    from core import settings
    con = demo.connect(tmp_path / "demo.db")
    subs.register(111, "B1", "", REF, con)
    settings.save(urgent_mode="resumen")
    ch = FakeChannel()
    rep = notifier.notify(alert("N008"), "test", True, con, ch, REF, background=False)
    assert not rep.urgent and rep.chats == [111] and ch.sent == []
    assert "/resumen" in rep.text() and subs.sent("N008", con)[0]["status"] == "pendiente"
