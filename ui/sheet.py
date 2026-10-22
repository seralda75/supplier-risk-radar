"""Ficha de proveedor en una ventana modal (st.dialog) que se abre desde cualquier vista: un punto del
mapa, una casilla del treemap, una fila del ranking o el buscador de la página Proveedores. Una casilla
que agrupa proveedores sin riesgo abre la lista de esos proveedores, y desde ella, cada ficha.

El clic solo deja la petición en session_state; open_requested() abre la ventana en esa misma ejecución
(st.dialog no puede abrirse desde un callback).
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from core.countdown import alternate_margin
from core.feedback import VERDICTS
from core.labels import CATEGORY_ES, CRITICALITY_ES, material_es, place_es, product_es, short_supplier
from core.recurrence import BUYERS, day_es, habitual_label, recurrence, transit_label
from core.schemas import EVENT_LABELS_ES
from core.suppliers import load_suppliers
from core.urgency import dependency

from . import cache
from .components import esc, head, md, table, tip
from .data import meur, signed, status_chip

SPLIT_ES = {"test": "Test", "validation": "Validación", "train": "Entrenamiento"}
LATE_ALTERNATE = 0.2     # suma al índice si el alternativo no llega antes de que se acabe el stock
PLOTLY_CONFIG = {"topojsonURL": "app/static/topojson/", "displaylogo": False, "displayModeBar": False}


def vulnerability(s) -> tuple[float, list[str]]:
    """Índice de vulnerabilidad sin eventos (CLAUDE.md, 8.2): la dependencia que decide la urgencia
    (único, criticidad, días de stock) + 0,2 si el alternativo aprobado no llega a tiempo."""
    d = dependency(s)
    score, factors = d.score, list(d.factors)
    if s.alternate_id and s.inventory_cover_days is not None and not alternate_margin(s, set()).in_time:
        score += LATE_ALTERNATE
        factors.append("el alternativo no llega a tiempo")
    return round(min(score, 1.0), 2), factors


def alt_text(s) -> tuple[str, bool]:
    """(texto del alternativo, ¿llega a tiempo?)."""
    sup = load_suppliers()
    if not s.alternate_id:
        return ("ninguno (único)" if s.single_source else "sin alternativo"), False
    cover = alternate_margin(s, set())
    name = short_supplier(sup[s.alternate_id].name)
    if s.inventory_cover_days is None:
        return f"{name} · plazo {cover.lead_days or 0:.0f} d", True
    if cover.in_time:
        return f"{name} · llega en {cover.lead_days:.0f} d", True
    return f"{name} · tarda {cover.lead_days or 0:.0f} d, no llega", False


def purchases_html(sid: str) -> str:
    """«Proveedor habitual · 12 pedidos» y el pedido en tránsito (historial de pedidos sintético)."""
    r = recurrence(sid)
    label = habitual_label(r)
    if not r.orders_12m:
        return f'<div class="buy"><span class="chip grey">{esc(label)}</span></div>'
    last = r.last_order
    who = BUYERS.get(last.buyer_id, {}).get("name", "")
    sub = (f"{r.orders_6m} pedidos en 6 meses · {r.consecutive} meses seguidos · último el "
           f"{day_es(last.day)}{' · ' + who if who else ''} · historial sintético (el reto no lo incluye)")
    transit = transit_label(r)
    return (f'<div class="buy"><span class="chip {"green" if r.recurrent else "grey"}">{esc(label)}</span>'
            f'{tip(sub)}'
            f'<span class="t"><span aria-hidden="true">🚚</span> En tránsito: <strong>{esc(transit)}</strong></span>'
            '</div>')


# ---------------------------------------------------------------------------
# Abrir la ficha desde un clic
# ---------------------------------------------------------------------------

def request(sid: str) -> None:
    """Callback: pide abrir la ficha de `sid`."""
    if sid in load_suppliers():
        st.session_state["sheet"] = sid


def request_list(title: str, ids: list[str]) -> None:
    """Pide abrir la lista de unos proveedores (p. ej. «Otros sin riesgo» del treemap)."""
    st.session_state["sheet_list"] = (title, list(ids))


def _picked(key: str, ver: int) -> None:
    sel = st.session_state.get(f"{key}-{ver}")
    points = (sel or {}).get("selection", {}).get("points", [])
    if not points:
        return
    pt = points[0]
    cd = pt.get("customdata")
    sid = pt.get("id") or (cd[0] if isinstance(cd, list) and cd else cd)
    if isinstance(sid, str):
        request(sid)
    # Gráfico nuevo (sin selección): un segundo clic en el mismo punto vuelve a abrir la ficha
    st.session_state[f"{key}-v"] = ver + 1


def clickable_chart(fig: go.Figure, key: str) -> None:
    """Gráfico de Plotly en el que pulsar un proveedor abre su ficha (customdata[0] o id = ID)."""
    ver = st.session_state.get(f"{key}-v", 0)
    st.plotly_chart(fig, width="stretch", key=f"{key}-{ver}", on_select=lambda: _picked(key, ver),
                    selection_mode="points", config=PLOTLY_CONFIG)


def open_requested() -> None:
    """Al final de cada página (y del fragmento del centro de control): abre la ficha o la lista pedida."""
    sid = st.session_state.pop("sheet", None)
    group = st.session_state.pop("sheet_list", None)
    if sid:
        _dialog(sid)
    elif group:
        _list_dialog(*group)


@st.dialog("Ficha de proveedor", width="large")
def _dialog(sid: str) -> None:
    render(sid)


@st.dialog("Proveedores sin riesgo", width="medium")
def _list_dialog(title: str, ids: list[str]) -> None:
    sup = load_suppliers()
    ids = sorted(ids, key=lambda i: -(sup[i].annual_spend_eur or 0))
    md(f'<h2 class="det-name">{esc(title)}{tip("Ninguna alerta activa · pulsa uno para ver su ficha")}</h2>')
    for i in ids:
        s = sup[i]
        with st.container(key=f"rk-l{i}"):
            md(f'<div class="rk lst"><span><strong>{esc(s.name)}</strong><span class="w">'
               f'{esc(place_es(s.city, s.country))}</span></span>'
               f'<span>{esc(material_es(s.material))}</span>'
               f'<span class="num r">{meur(s.annual_spend_eur or 0)} M€</span>'
               '<span class="go" aria-hidden="true">›</span></div>')
            if st.button(f"Ficha de {s.name}", key=f"rkbtn-l{i}"):
                request(i)
                st.rerun()          # cierra la lista y, en la ejecución siguiente, abre la ficha


# ---------------------------------------------------------------------------
# Contenido de la ficha
# ---------------------------------------------------------------------------

def render(sid: str) -> None:
    sup = load_suppliers()
    s = sup[sid]
    score, factors = vulnerability(s)
    alt, ok = alt_text(s)
    chips = ['<span class="chip red">Proveedor único</span>' if s.single_source else
             '<span class="chip green">Con alternativo</span>',
             f'<span class="chip grey">Criticidad {CRITICALITY_ES.get(s.criticality, s.criticality)}</span>']
    stock = f"{s.inventory_cover_days:.0f} días" if s.inventory_cover_days is not None else "sin stock"
    lead = f"{s.lead_time_days:.0f} días" if s.lead_time_days is not None else "—"
    for en, es in CRITICALITY_ES.items():
        factors = [f.replace(f"criticidad {en}", f"criticidad {es.lower()}") for f in factors]
    why = f"Vulnerable por: {', '.join(factors)}" if factors else "Sin factores de vulnerabilidad"
    md(f'<div style="display:flex;flex-direction:column;gap:10px"><h2 class="det-name">{esc(s.name)}</h2>'
       f'<span class="det-sub">{esc(place_es(s.city, s.country))} · {esc(material_es(s.material))}</span>'
       f'<span class="sheet-chips">{"".join(chips)}</span></div>')
    md(purchases_html(sid))
    md(f'<div class="boxes"><div class="box"><span class="l">Stock</span><span class="num v">{stock}</span></div>'
       f'<div class="box"><span class="l">Plazo de entrega</span><span class="num v">{lead}</span></div>'
       f'<div class="box"><span class="l">Gasto anual</span><span class="num v">{meur(s.annual_spend_eur or 0)} M€'
       f'</span></div>'
       f'<div class="box {"" if ok else "amber"}"><span class="l">Alternativo{tip(f"{why} · índice {score:.2f}")}'
       f'</span><span class="t" style="font-size:16px">{esc(alt)}</span></div></div>')
    prods = ", ".join(product_es(p) for p in s.products)
    if prods:
        md(f'<p class="what" style="font-size:15px"><strong>Medicamentos:</strong> {esc(prods)}</p>')
    md('<h3 class="h3">Historial</h3>' + history(sid))


def history(sid: str) -> str:
    rows = []
    for sp, d in cache.all_data().items():
        if not d:
            continue
        alerts = {a.id: a for a in cache.alerts(sp)}
        fb = cache.decisions(sp)
        for r in d["results"]:
            if sid not in r["affected_ids"]:
                continue
            a = alerts.get(r["news_id"])
            c = next((x for x in r.get("countdown", []) if x["supplier_id"] == sid), None)
            if a:
                text, color = status_chip(a)
                state = f'<span class="chip {color}">{esc(text)}</span>'
            else:
                state = '<span class="chip grey">Sin riesgo</span>'
            margin = (f'<span class="num">{signed(c["margin_days"])} d</span>'
                      if c and c["inventory_days"] is not None else "—")
            rows.append([f'<span class="num">{esc((r.get("published_date") or "")[:10])}</span>',
                         f'<span title="{SPLIT_ES[sp]} · {esc(r["news_id"])}">{esc(r["headline"])}</span>',
                         state, margin])
    rows.sort(key=lambda x: x[0], reverse=True)
    if not rows:
        return '<p class="sub">Sin noticias.</p>'
    return table(["Fecha", "Noticia", "Estado", "Margen"], rows, right={3})

