"""Ajustes: lo mínimo que un director de compras toca, agrupado. Todo afecta solo al panel.

Noticias (cargar un xlsx o csv y volver a las del día) · IA · Criterios de riesgo · Notificaciones · Datos y demo.
Los valores se guardan en data/settings.json (core/settings.py). Ni el pipeline evaluado ni fill_test.py los leen.
"""
from __future__ import annotations

import streamlit as st

from core import custom_news
from core.suppliers import load_suppliers  # noqa: F401  (calienta la caché de fichas antes de procesar)

from . import cache
from .components import esc, head, md


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
# Página
# ---------------------------------------------------------------------------

def render() -> None:
    if toast := st.session_state.pop("toast", None):
        st.toast(toast[0], icon=toast[1])
    md('<h1 class="h1">Ajustes</h1>')
    news_group()
