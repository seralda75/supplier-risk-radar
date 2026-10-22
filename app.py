"""Panel Supplier Risk Radar (Streamlit), con el diseño de docs/mockup_centro_control.html.

    streamlit run app.py

Para el director de compras: en 5 segundos, si hay riesgo, dónde, cuánto tiempo queda y qué hacer.
Páginas (views/, una por fichero; st.navigation solo ejecuta la activa): Centro de control ·
Proveedores · Simulador «¿Y si…?» · Transparencia. El contenido de cada una está en ui/.

Lee los resultados guardados (data/results/*.json, de scripts/build_results.py): al abrir no se llama
al LLM y funciona sin internet (fuentes y mapa servidos desde static/). Lo único que puede llamar al
LLM es «Interpretar» en el simulador, y solo cuando el usuario lo pulsa. Las decisiones (aprobar plan,
falsa alarma, reabrir) se guardan en SQLite (core/feedback.py).
"""
from __future__ import annotations

import streamlit as st

from core import demo
from ui import cache
from ui import theme as T
from ui.components import esc, md
from ui.data import when

st.set_page_config(page_title="Supplier Risk Radar · Helixa", page_icon="📡", layout="wide",
                   initial_sidebar_state="expanded")
st.html(T.BASE_CSS)            # todo el estilo en una sola llamada (constante calculada al importar)
st.session_state.setdefault("split", "test")

PAGES = {
    "control": st.Page("views/control.py", title="Centro de control", default=True),
    "calendar": st.Page("views/calendar.py", title="Calendario", url_path="calendario"),
    "suppliers": st.Page("views/suppliers.py", title="Proveedores", url_path="proveedores"),
    "simulator": st.Page("views/simulator.py", title="Simulador «¿Y si…?»", url_path="simulador"),
    "transparency": st.Page("views/transparency.py", title="Transparencia", url_path="transparencia"),
}
current = st.navigation(list(PAGES.values()), position="hidden")

# ---------------------------------------------------------------------------
# Navegación lateral: enlaces reales a cada página (la activa lleva la clave navon-)
# ---------------------------------------------------------------------------
with st.sidebar:
    md(f'<div class="nav-brand">{T.RADAR_LOGO}<div><span class="t">Supplier Risk Radar</span>'
       '<span class="s">Helixa Pharmaceuticals</span></div></div>')
    for key, page in PAGES.items():
        with st.container(key=f"{'navon' if page.title == current.title else 'nav'}-{key}"):
            st.page_link(page, label=page.title, width="stretch")
    loaded = cache.all_data()
    up = cache.llm_up()
    n_news = sum(len(d["results"]) for d in loaded.values() if d)
    stamp = max((d["generated"] for d in loaded.values() if d), default="")
    # Modo demo (discreto, al pie del menú): noticias que «llegan» en directo, con su propia base de datos.
    # También se activa abriendo la app con ?demo=1.
    st.session_state.setdefault("demo", st.query_params.get("demo") == "1")
    with st.container(key="navdemo"):
        st.toggle("Modo demo", key="demo", on_change=lambda: st.session_state["demo"] and demo.warm_up(),
                  help="Simula noticias entrantes en el centro de control. Usa data/demo.db: no toca la entrega "
                       "ni data/app.db")
        if st.session_state["demo"]:
            demo.warm_up()
            st.toggle("IA en directo", key="demo_live", value=True,
                      help="Encendido: llamada real a la IA local (más lenta). Apagado: la respuesta en caché")
    tg_ok, tg = cache.telegram()
    with st.container(key="navfoot"):
        md(f'<div class="nav-foot"><span><span class="dot" style="background:{"#4CAF7A" if up else "#A9A3B6"}">'
           f'</span>{"Sistema operativo · local" if up else "Modo lectura · IA local apagada"}</span>'
           f'<span class="tg"><span class="dot" style="background:{"#4CAF7A" if tg_ok else "#A9A3B6"}"></span>'
           f'{esc(tg)}</span>'
           f'<span>Datos a {esc(when(stamp))}</span><span>{n_news} noticias analizadas</span></div>')

current.run()
