"""Radar Bot (bot/telegram_bot.py): comandos con un Update y un contexto falsos, sin red ni token real."""
import asyncio
import re
from types import SimpleNamespace

from bot import telegram_bot as tb
from core import feedback, subscriptions as subs


class Msg:
    def __init__(self):
        self.sent = []

    async def reply_text(self, text, **kw):
        self.sent.append((text, kw.get("reply_markup")))


class Query:
    def __init__(self, data):
        self.data, self.edited, self.answered = data, [], []

    async def answer(self, text=None, **kw):
        self.answered.append(text)

    async def edit_message_text(self, text, **kw):
        self.edited.append(text)


def fake(con, chat_id=111, args=(), data=None):
    msg = Msg()
    upd = SimpleNamespace(effective_chat=SimpleNamespace(id=chat_id, full_name="Móvil de prueba", title=None),
                          effective_message=msg, callback_query=Query(data) if data else None)
    ctx = SimpleNamespace(bot_data={"con": con, "demo": True}, args=list(args))
    return upd, ctx, msg


def run(handler, upd, ctx):
    asyncio.run(handler(upd, ctx))


def test_buscar_proveedor_por_id_nombre_o_parecido():
    assert [s.id for s in subs.find_suppliers("s015")] == ["S015"]
    assert [s.id for s in subs.find_suppliers("Lumina")] == ["S015"]
    assert [s.id for s in subs.find_suppliers("nordic lipid")] == ["S012"]
    assert {s.id for s in subs.find_suppliers("Rotterdam")} == {"S038"}
    assert subs.find_suppliers("zzzz") == []


def test_start_ofrece_los_tres_compradores_y_registra(tmp_path):
    con = feedback.connect(tmp_path / "a.db")
    upd, ctx, msg = fake(con)
    run(tb.start, upd, ctx)
    text, markup = msg.sent[0]
    assert "modo demo" in text
    assert [row[0].callback_data for row in markup.inline_keyboard] == ["reg|B1", "reg|B2", "reg|B3"]
    upd, ctx, _ = fake(con, data="reg|B2")
    run(tb.on_register, upd, ctx)
    assert "Pablo Navarro" in upd.callback_query.edited[0]
    assert subs.buyer(111, con)["buyer_id"] == "B2"


def test_seguir_dejar_y_mis_proveedores(tmp_path):
    con = feedback.connect(tmp_path / "a.db")
    upd, ctx, msg = fake(con, args=["Lumina"])
    run(tb.seguir, upd, ctx)
    assert "regístrate" in msg.sent[0][0]                   # sin /start no se puede seguir
    subs.register(111, "B3", con=con)
    upd, ctx, msg = fake(con, args=["Celsius"])
    run(tb.seguir, upd, ctx)
    assert "Ahora sigues a <b>Celsius Bioprocess Systems</b>" in msg.sent[0][0]
    upd, ctx, msg = fake(con)
    run(tb.mis_proveedores, upd, ctx)
    text = msg.sent[0][0]
    assert "Celsius" in text and "seguido a mano" in text and re.search(r"habitual · \d+ pedidos", text)
    upd, ctx, msg = fake(con, args=["S025"])
    run(tb.dejar, upd, ctx)
    assert "Ya no sigues" in msg.sent[0][0]
    upd, ctx, msg = fake(con, args=["S025"])
    run(tb.dejar, upd, ctx)
    assert "No seguías" in msg.sent[0][0]
    upd, ctx, msg = fake(con, args=[])
    run(tb.seguir, upd, ctx)
    assert "Indica el proveedor" in msg.sent[0][0]


def test_resumen_envia_las_pendientes_una_sola_vez(tmp_path):
    con = feedback.connect(tmp_path / "a.db")
    subs.register(111, "B1", con=con)
    subs.claim(111, "test", "N050", "resumen", ["S011"], "<b>Iberia</b> · dificultades financieras", con)
    upd, ctx, msg = fake(con)
    run(tb.resumen, upd, ctx)
    assert "Resumen semanal" in msg.sent[0][0] and "Iberia" in msg.sent[0][0]
    upd, ctx, msg = fake(con)
    run(tb.resumen, upd, ctx)
    assert "Sin alertas no urgentes" in msg.sent[0][0]


def test_el_bot_se_construye_sin_red(tmp_path, monkeypatch):
    monkeypatch.setattr(tb.config, "connect", lambda demo: feedback.connect(tmp_path / "a.db"))
    app = tb.build("123456:TEST", demo=True)
    assert app.bot_data["demo"] is True and app.handlers


def test_el_token_no_sale_en_los_logs(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:SECRETO")
    assert tb.config.redact("GET https://api.telegram.org/bot123456:SECRETO/getMe") == \
        "GET https://api.telegram.org/bot<token>/getMe"
