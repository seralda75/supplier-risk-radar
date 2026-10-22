"""Radar Bot de Telegram para los compradores de Helixa (python-telegram-bot v21+, polling: sin URL pública).

    python -m bot.telegram_bot            # con data/app.db
    python -m bot.telegram_bot --demo     # con data/demo.db, la del «Modo demo» del panel

Comandos:
    /start              registra el chat y elige el comprador ficticio (botones)
    /seguir <proveedor> /dejar <proveedor>   por ID o nombre («S015», «Lumina»)
    /mis_proveedores    proveedores que sigue el chat (habituales y manuales)
    /resumen            alertas no urgentes de la semana

Los avisos los envía bot/notifier.py (desde el panel o el pipeline); este proceso atiende los comandos y los
botones de esos avisos. El token se lee de .env y no se imprime.
"""
from __future__ import annotations

import argparse
import html
import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update   # noqa: E402
from telegram.constants import ParseMode                                    # noqa: E402
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler,  # noqa: E402
                          ContextTypes)

from bot import config                                                      # noqa: E402
from core import subscriptions as subs                                      # noqa: E402
from core.labels import short_supplier                                      # noqa: E402
from core.recurrence import BUYERS, recurrence                              # noqa: E402
from core.suppliers import load_suppliers                                   # noqa: E402

log = logging.getLogger("radar_bot")
HELP = ("<b>Radar Bot · Helixa</b>\n"
        "Te aviso al momento de las alertas urgentes de tus proveedores habituales.\n\n"
        "/seguir &lt;proveedor&gt; · /dejar &lt;proveedor&gt;\n"
        "/mis_proveedores · /resumen (alertas no urgentes de la semana)")


def e(text) -> str:
    """Escapa texto para el formato HTML de Telegram."""
    return html.escape(str(text), quote=False)


def db(context: ContextTypes.DEFAULT_TYPE) -> sqlite3.Connection:
    return context.bot_data["con"]


def is_demo(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return context.bot_data["demo"]


async def reply(update: Update, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup,
                                              disable_web_page_preview=True)


def _registered(update: Update, context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    return subs.buyer(update.effective_chat.id, db(context))


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = [[InlineKeyboardButton(f"{b['name']} · {b['area']}", callback_data=f"reg|{bid}")]
            for bid, b in BUYERS.items()]
    mode = " (modo demo)" if is_demo(context) else ""
    await reply(update, f"<b>Radar Bot · Helixa</b>{mode}\n¿Qué comprador eres? (compradores ficticios de la demo)",
                InlineKeyboardMarkup(rows))


async def on_register(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    bid = q.data.split("|")[1]
    chat = update.effective_chat
    subs.register(chat.id, bid, chat.full_name or chat.title or "", con=db(context))
    n = len(subs.followed(chat.id, db(context)))
    await q.answer("Registrado")
    b = BUYERS[bid]
    await q.edit_message_text(f"✅ Registrado como <b>{e(b['name'])}</b> ({e(b['area'])}).\n"
                              f"Sigues a tus <b>{n}</b> proveedores habituales.\n\n{HELP}", parse_mode=ParseMode.HTML)


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, HELP)


def _pick(args: list[str]) -> tuple[object | None, str]:
    """El proveedor de /seguir o /dejar, o un mensaje de error."""
    text = " ".join(args).strip()
    if not text:
        return None, "Indica el proveedor: por ejemplo <code>/seguir S015</code> o <code>/seguir Lumina</code>."
    found = subs.find_suppliers(text)
    if not found:
        return None, f"No encuentro ningún proveedor «{e(text)}»."
    if len(found) > 1:
        names = "\n".join(f"· {s.id} {e(s.name)}" for s in found[:8])
        return None, f"Hay varios proveedores con «{e(text)}». Indica el ID:\n{names}"
    return found[0], ""


async def seguir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _registered(update, context):
        await reply(update, "Primero regístrate con /start.")
        return
    s, err = _pick(context.args)
    if not s:
        await reply(update, err)
        return
    subs.follow(update.effective_chat.id, s.id, db(context))
    await reply(update, f"👀 Ahora sigues a <b>{e(s.name)}</b> ({s.id}).")


async def dejar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _registered(update, context):
        await reply(update, "Primero regístrate con /start.")
        return
    s, err = _pick(context.args)
    if not s:
        await reply(update, err)
        return
    if subs.unfollow(update.effective_chat.id, s.id, db(context)):
        await reply(update, f"Ya no sigues a <b>{e(s.name)}</b> ({s.id}).")
    else:
        await reply(update, f"No seguías a <b>{e(s.name)}</b> ({s.id}).")


async def mis_proveedores(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    b = _registered(update, context)
    if not b:
        await reply(update, "Primero regístrate con /start.")
        return
    subs.sync_auto(b["chat_id"], con=db(context))
    sup = load_suppliers()
    lines = []
    for f in subs.followed(b["chat_id"], db(context)):
        s = sup.get(f["supplier_id"])
        if not s:
            continue
        r = recurrence(s.id, buyer_id=b["buyer_id"])
        tag = f"habitual · {r.orders_12m} pedidos" if f["origin"] == "auto" else "seguido a mano"
        lines.append(f"· {s.id} <b>{e(short_supplier(s.name))}</b> · {tag}")
    body = "\n".join(lines) or "No sigues a ningún proveedor."
    await reply(update, f"<b>{e(b['name'])}</b> ({e(BUYERS[b['buyer_id']]['area'])}) sigue a:\n{body}")


async def resumen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    b = _registered(update, context)
    if not b:
        await reply(update, "Primero regístrate con /start.")
        return
    rows = subs.pending_summary(b["chat_id"], con=db(context))
    if not rows:
        await reply(update, "📋 Sin alertas no urgentes nuevas esta semana para tus proveedores.")
        return
    lines = [f"· {r['line']}" for r in rows]           # cada línea ya viene escapada del notificador
    await reply(update, "📋 <b>Resumen semanal</b> · alertas no urgentes\n" + "\n".join(lines))
    for r in rows:
        subs.mark(r["id"], "resumido", con=db(context))


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

def build(token: str, demo: bool) -> Application:
    app = Application.builder().token(token).build()
    app.bot_data["demo"] = demo
    app.bot_data["con"] = config.connect(demo)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["ayuda", "help"], ayuda))
    app.add_handler(CommandHandler("seguir", seguir))
    app.add_handler(CommandHandler("dejar", dejar))
    app.add_handler(CommandHandler("mis_proveedores", mis_proveedores))
    app.add_handler(CommandHandler("resumen", resumen))
    app.add_handler(CallbackQueryHandler(on_register, pattern=r"^reg\|"))
    return app


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="usa data/demo.db (la del «Modo demo» del panel)")
    args = ap.parse_args()
    token = config.token()
    if not token:
        sys.exit("Falta TELEGRAM_BOT_TOKEN en .env: el bot no arranca (el panel funciona igual).")
    logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s", level=logging.INFO)
    # httpx registraría cada petición con la URL completa, que incluye el token: solo avisos, y el token tapado
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for h in logging.getLogger().handlers:
        h.addFilter(config.RedactToken())
    print(f"Radar Bot en marcha ({'modo demo · data/demo.db' if args.demo else 'data/app.db'}). Ctrl+C para parar.",
          flush=True)
    build(token, args.demo).run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
