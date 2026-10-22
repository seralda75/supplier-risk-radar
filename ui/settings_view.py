"""Ajustes: lo mínimo que un director de compras toca, agrupado. Todo afecta solo al panel.

Noticias (cargar un xlsx o csv y volver a las del día) · IA · Criterios de riesgo · Notificaciones · Datos y demo.
Los valores se guardan en data/settings.json (core/settings.py). Ni el pipeline evaluado ni fill_test.py los leen.
"""
from __future__ import annotations

import csv
import io

import streamlit as st

from core import audit, custom_news, demo, feedback, settings, subscriptions
from core.config import LLM_MODEL, ROOT

from . import cache
from .components import esc, head, md

DELIVERABLE = "Supplier_Risk_3_Test_respuestas.xlsx"


def _row(label: str, value: str) -> str:
    return f'<div class="srow"><span class="l">{esc(label)}</span><span class="v">{esc(value)}</span></div>'


# ---------------------------------------------------------------------------
# Noticias
# ---------------------------------------------------------------------------

def _close_load() -> None:
    st.session_state.pop("load_dialog", None)


def _process(news: list[dict], name: str) -> None:
    """Pasa las noticias por el pipeline con una barra de progreso y las activa como fuente del panel."""
    bar = st.progress(0.0, text="Procesando…")

    def progress(done: int, total: int, headline: str) -> None:
        bar.progress(done / total, text=f"Noticia {min(done + 1, total)} de {total}" + (f" · {headline[:60]}" if headline else ""))
    custom_news.process(news, name=name, progress=progress)
    custom_news.use(True)
    st.session_state.pop("load_dialog", None)
    st.session_state["toast"] = (f"{len(news)} noticias cargadas y procesadas", "✅")
    st.rerun()


@st.dialog("Cargar noticias", width="medium", on_dismiss=_close_load)
def load_dialog() -> None:
    md(f'<p class="sub">Columnas: {esc(", ".join(custom_news.REQUIRED))}</p>')
    up = st.file_uploader("Fichero", type=["xlsx", "csv"], key="news_file", label_visibility="collapsed")
    if up is None:
        return
    try:
        news = custom_news.read(up.getvalue(), up.name)
    except custom_news.NewsFileError as e:
        st.error(str(e))
        return
    md(f'<p class="what">{len(news)} noticias válidas.</p>')
    if st.button("Procesar noticias", type="primary", key="news_process", width="stretch"):
        _process(news, up.name)


def _back_to_default() -> None:
    custom_news.use(False)
    st.session_state["toast"] = ("Vuelves a las noticias del día", "↩️")


def _use_loaded() -> None:
    custom_news.use(True)
    st.session_state["toast"] = ("Usas las noticias cargadas", "✅")


def _reprocess() -> None:
    stored = custom_news.stored_input()
    if stored:
        st.session_state["reprocess"] = stored


def news_group() -> None:
    info = custom_news.info()
    active = custom_news.active()
    with st.container(key="panel-set-news"):
        md(head("Noticias", "Por defecto, las noticias del test ya procesadas. Cargar un fichero no toca la "
                "entrega ni los resultados guardados."))
        md(_row("Fuente activa", cache.source_label()))
        if info:
            md(_row("Última carga", f"{info['name'] or 'sin nombre'} · {info['news']} noticias · "
                                    f"{info['loaded_at'].replace('T', ' ')[:16]}"))
        c1, c2, c3 = st.columns(3)
        if c1.button("Cargar noticias", key="news_load", type="primary", width="stretch"):
            st.session_state["load_dialog"] = True
        if active:
            c2.button("Volver a las noticias del día", key="news_back", on_click=_back_to_default, width="stretch")
        elif info:
            c2.button("Usar las cargadas", key="news_use", on_click=_use_loaded, width="stretch")
        if info:
            c3.button("Reprocesar", key="news_reprocess", on_click=_reprocess, width="stretch",
                      help="Vuelve a pasar el último fichero por el pipeline")
    if (stored := st.session_state.pop("reprocess", None)):
        _process(stored[1], stored[0])
    if st.session_state.get("load_dialog"):
        load_dialog()


# ---------------------------------------------------------------------------
# IA, criterios, notificaciones, datos y demo
# ---------------------------------------------------------------------------

NUMBERS = {"set-timeout": "ai_timeout_s", "set-margin": "margin_tight_days", "set-urgent-days": "urgent_buy_days",
           "set-recurrent": "recurrent_min"}
WIDGETS = {**NUMBERS, "set-live": "live_ai", "set-mode": "urgent_mode"}


MODES = {"Al momento": "inmediato", "En el resumen": "resumen"}


def _k(widget: str) -> str:
    """Clave del control. «Restablecer» cambia la versión: los controles nacen de nuevo con el valor por defecto
    (fijar session_state no basta: el navegador conserva el valor anterior y lo volvería a enviar)."""
    ver = st.session_state.get("set-ver", 0)
    return f"{widget}~{ver}" if ver else widget


def _save(widget: str) -> None:
    """Guarda al cambiar un control (sin botón «Guardar»)."""
    value = st.session_state[_k(widget)]
    if widget == "set-mode":
        value = MODES[value]
    settings.save(**{WIDGETS[widget]: value})


def _reset() -> None:
    settings.reset()
    st.session_state["set-ver"] = st.session_state.get("set-ver", 0) + 1
    st.session_state["toast"] = ("Valores por defecto restablecidos", "↩️")


def ai_group(cfg: dict) -> None:
    up = cache.llm_up()
    with st.container(key="panel-set-ai"):
        md(head("IA", "La IA local (Ollama) lee las noticias. «En directo» llama al modelo en la demo; apagado, "
                "usa la respuesta en caché. Si tarda más del máximo, se usa el resultado precalculado."))
        md(_row("Ollama", "activo" if up else "apagado (modo lectura)") + _row("Modelo", LLM_MODEL))
        c1, c2 = st.columns(2, vertical_alignment="bottom")
        c1.toggle("IA en directo", value=cfg["live_ai"], key=_k("set-live"), on_change=_save, args=("set-live",),
                  help="Solo afecta a «Simular noticia entrante» del modo demo")
        c2.number_input("Tiempo máximo (s)", min_value=10, max_value=600, step=10, value=cfg["ai_timeout_s"],
                        key=_k("set-timeout"), on_change=_save, args=("set-timeout",))


def criteria_group(cfg: dict) -> None:
    with st.container(key="panel-set-criteria"):
        md(head("Criterios de riesgo", "Solo cambian el calendario, los colores del margen y quién es proveedor "
                "habitual en el panel. El diagnóstico de la entrega usa siempre la configuración evaluada."))
        c1, c2, c3 = st.columns(3)
        c1.number_input("Margen ajustado (días)", min_value=1, max_value=60, value=cfg["margin_tight_days"],
                        key=_k("set-margin"), on_change=_save, args=("set-margin",),
                        help="Por debajo, el margen se considera ajustado")
        c2.number_input("Compra urgente (días)", min_value=1, max_value=60, value=cfg["urgent_buy_days"],
                        key=_k("set-urgent-days"), on_change=_save, args=("set-urgent-days",),
                        help="Plazo de una compra urgente sin alternativo libre")
        c3.number_input("Proveedor habitual (pedidos en 6 meses)", min_value=1, max_value=6,
                        value=cfg["recurrent_min"], key=_k("set-recurrent"), on_change=_save,
                        args=("set-recurrent",))
        st.button("Restablecer valores por defecto", key="set-reset", on_click=_reset)


def notifications_group(cfg: dict) -> None:
    ok, text = cache.telegram()
    # los chats se registran en la base con la que arranca el bot (app.db, o demo.db con --demo): se cuentan las dos
    buyers = list({b["chat_id"]: b for con in (cache.db(), cache.demo_db())
                   for b in subscriptions.chats(con)}.values())
    with st.container(key="panel-set-notify"):
        md(head("Notificaciones", "El token de Telegram se lee de .env y nunca se muestra."))
        md(_row("Telegram", text) + _row("Compradores registrados", str(len(buyers)) + (
            " · " + ", ".join(b["name"] for b in buyers) if buyers else "")))
        st.radio("Alertas urgentes", list(MODES), index=list(MODES.values()).index(cfg["urgent_mode"]),
                 horizontal=True, key=_k("set-mode"), on_change=_save, args=("set-mode",),
                 help="Al momento: aviso inmediato. En el resumen: se agrupan en /resumen")


def _audit_csv() -> bytes:
    """Auditoría en CSV: los análisis del pipeline (core/audit) y las decisiones de los compradores."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["tipo", "fecha", "noticia", "detalle", "resultado", "usuario", "canal"])
    try:
        for r in audit.history(5000).to_dict("records"):
            w.writerow(["análisis", r["ts"], r["news_id"], r["headline"],
                        f"riesgo={'sí' if r['is_risk'] else 'no'}; urgente={'sí' if r['urgent'] else 'no'}; "
                        f"proveedores={r['affected_ids']}", "", r["mode"]])
    except Exception:                    # sin auditoría todavía: solo las decisiones
        pass
    for r in feedback.history(5000, cache.db()):
        w.writerow(["decisión", r["ts"], r["news_id"], r["note"], feedback.VERDICTS.get(r["verdict"], r["verdict"]),
                    r["user"], r["channel"]])
    return out.getvalue().encode("utf-8-sig")


def _reset_demo() -> None:
    demo.reset(cache.demo_db())
    for k in ("demo_new", "alert_dialog"):
        st.session_state.pop(k, None)
    st.session_state["toast"] = ("Demo reiniciada: todo como al principio", "🔄")


def _set_demo() -> None:
    st.session_state["demo"] = st.session_state["set-demo"]
    if st.session_state["demo"]:
        demo.warm_up()


def data_group() -> None:
    st.session_state["set-demo"] = cache.demo_on()      # el interruptor del menú y este van a la par
    with st.container(key="panel-set-data"):
        md(head("Datos y demo", "La demo usa data/demo.db: no toca la entrega ni data/app.db. «Reiniciar demo» "
                "conserva los chats de Telegram registrados."))
        st.toggle("Modo demo", key="set-demo", on_change=_set_demo)
        c1, c2, c3 = st.columns(3)
        c1.button("Reiniciar demo", key="set-demo-reset", on_click=_reset_demo, width="stretch")
        c2.download_button("Exportar auditoría (CSV)", data=_audit_csv(), file_name="auditoria.csv",
                           mime="text/csv", key="set-audit", width="stretch")
        deliverable = ROOT / "deliverables" / DELIVERABLE
        if deliverable.exists():
            c3.download_button("Descargar la entrega (xlsx)", data=deliverable.read_bytes(), file_name=DELIVERABLE,
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key="set-deliverable", width="stretch")


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------

def render() -> None:
    if toast := st.session_state.pop("toast", None):
        st.toast(toast[0], icon=toast[1])
    md('<h1 class="h1">Ajustes</h1>')
    cfg = settings.load()
    news_group()
    ai_group(cfg)
    criteria_group(cfg)
    notifications_group(cfg)
    data_group()
