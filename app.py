"""Panel Supplier Risk Radar (Streamlit), con el diseño de docs/mockup_centro_control.html.

    streamlit run app.py

Para el director de compras: en 5 segundos, si hay riesgo, dónde, cuánto tiempo queda y qué hacer.
Vistas: Centro de control · Proveedores · Simulador «¿Y si…?» · Transparencia (paquete ui/).

Lee los resultados guardados (data/results/*.json, de scripts/build_results.py): al abrir no se llama
al LLM y funciona sin internet (fuentes y mapa servidos desde static/). Lo único que puede llamar al
LLM es «Interpretar» en el simulador, y solo cuando el usuario lo pulsa. Las decisiones (aprobar plan,
falsa alarma) se guardan en SQLite (core/feedback.py).
"""
from __future__ import annotations

import streamlit as st

from core import llm, results
from ui import theme as T
from ui.components import esc, md
from ui.data import when

st.set_page_config(page_title="Supplier Risk Radar · Helixa", page_icon="📡", layout="wide",
                   initial_sidebar_state="expanded")

VIEWS = {"control": "Centro de control", "suppliers": "Proveedores", "simulator": "Simulador «¿Y si…?»",
         "transparency": "Transparencia"}
st.session_state.setdefault("view", "control")
st.session_state.setdefault("split", "test")


def go_to(view: str) -> None:
    st.session_state["view"] = view


view = st.session_state["view"]
st.markdown(T.BASE_CSS + T.nav_css(view), unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _load(split: str, mtime: float) -> dict | None:
    return results.load(split)


def get(split: str) -> dict | None:
    p = results.path(split)
    return _load(split, p.stat().st_mtime if p.exists() else 0.0)


# ---------------------------------------------------------------------------
# Navegación lateral
# ---------------------------------------------------------------------------
loaded = {sp: get(sp) for sp in results.SPLITS}
up = llm.is_up()
with st.sidebar:
    md(f'<div class="nav-brand">{T.RADAR_LOGO}<div><span class="t">Supplier Risk Radar</span>'
       '<span class="s">Helixa Pharmaceuticals</span></div></div>')
    for key, label in VIEWS.items():
        st.button(label, key=f"nav-{key}", on_click=go_to, args=(key,), width="stretch")
    n_news = sum(len(d["results"]) for d in loaded.values() if d)
    stamp = max((d["generated"] for d in loaded.values() if d), default="")
    with st.container(key="navfoot"):
        md(f'<div class="nav-foot"><span><span class="dot" style="background:{"#4CAF7A" if up else "#A9A3B6"}">'
           f'</span>{"Sistema operativo · local" if up else "Modo lectura · IA local apagada"}</span>'
           f'<span>Datos a {esc(when(stamp))}</span><span>{n_news} noticias analizadas</span></div>')

# ---------------------------------------------------------------------------
# Vista activa
# ---------------------------------------------------------------------------
split = st.session_state["split"]
if view == "control":
    from ui import control
    data = loaded.get(split)
    if not data:
        st.warning(f"No hay resultados guardados para «{results.SPLITS[split]}». "
                   f"Genéralos con `python scripts/build_results.py --split {split}`.")
    else:
        control.render(split, data, go_to)
elif view == "suppliers":
    from ui import suppliers_view
    suppliers_view.render(loaded)
elif view == "simulator":
    from ui import simulator
    simulator.render(llm_up=up)
else:
    from ui import transparency
    transparency.render(loaded)
