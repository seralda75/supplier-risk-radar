"""Piezas HTML/CSS reutilizables (KPIs, tablas, leyendas) y el mapa de proveedores (Plotly).

La figura del mapa se cachea (st.cache_data): con los mismos datos no se vuelve a construir. Cada
proveedor lleva su ID en customdata[0] para abrir su ficha al pulsarlo.
"""
from __future__ import annotations

import html
import math
import re

import plotly.graph_objects as go
import streamlit as st

from core.geo import coords
from core.labels import CITY_ES, short_supplier
from core.suppliers import load_suppliers

from . import theme as T

STATUS_DOT = {   # estado de la cuenta atrás -> (etiqueta de negocio, color del punto)
    "rotura_prevista": ("Rotura prevista", T.RED),
    "sin_inventario": ("Impacto inmediato (sin stock)", T.RED),
    "riesgo_latente": ("Riesgo latente", T.AMBER_DOT),
    "margen_ajustado": ("Margen ajustado", T.AMBER_DOT),
    "cubierto": ("Cubierto", T.GREEN),
}


def esc(x) -> str:
    return html.escape(str(x))


def md(fragment: str) -> None:
    """HTML propio en una sola línea (sin saltos: el parser de Markdown no lo toca)."""
    st.markdown(fragment.replace("\n", ""), unsafe_allow_html=True)


def tip(text: str) -> str:
    """ⓘ con el texto de ayuda como tooltip (title: se ve al pasar el ratón y al enfocarlo con el teclado)."""
    return f'<span class="tip" tabindex="0" role="img" aria-label="{esc(text)}" title="{esc(text)}">ⓘ</span>'


def kpi(label: str, value: str, unit: str = "", sub: str = "", color: str = "", alert: bool = False,
        text: bool = False) -> str:
    """Indicador del mockup: etiqueta, cifra y unidad. El texto de apoyo (sub, puede traer HTML) va en un
    tooltip ⓘ, no en la tarjeta. text=True para valores que son palabras (un país), en la fuente normal."""
    style = f' style="color:{color}"' if color else ""
    u = f'<span class="u">{esc(unit)}</span>' if unit else ""
    cls = "txt" if text else "num"
    note = tip(html.unescape(re.sub(r"<[^>]+>", "", sub))) if sub else ""
    return (f'<div class="kpi{" alert" if alert else ""}"><span class="k">{esc(label)}{note}</span>'
            f'<span class="v"><span class="{cls}"{style}>{esc(value)}</span>{u}</span></div>')


def kpis(items: list[str]) -> None:
    md('<section class="kpis" aria-label="Indicadores clave">' + "".join(items) + "</section>")


def table(headers: list[str], rows: list[list[str]], right: set[int] = frozenset()) -> str:
    """Tabla HTML con el estilo del panel. Las celdas ya vienen escapadas (pueden llevar HTML)."""
    th = "".join(f'<th class="{"r" if i in right else ""}">{esc(h)}</th>' for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(f'<td class="{"r" if i in right else ""}">{c}</td>' for i, c in enumerate(r))
                   + "</tr>" for r in rows)
    return f'<div class="tbl-wrap"><table class="tbl"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def head(title: str, note: str = "", hid: str = "") -> str:
    """Cabecera de tarjeta: título y, si hay nota, un ⓘ con ella como tooltip."""
    i = f' id="{hid}"' if hid else ""
    return f'<div class="card-head"><h2 class="h2"{i}>{esc(title)}{tip(note) if note else ""}</h2></div>'


def card(title: str, body: str, note: str = "") -> str:
    return f'<section class="card">{head(title, note)}{body}</section>'


def dot_legend(items: list[tuple[str, str]]) -> str:
    return ('<span class="legend">' + "".join(f'<span><span class="dot" style="background:{c}"></span>{esc(t)}</span>'
                                               for t, c in items) + "</span>")


@st.cache_data(show_spinner=False)
def risk_map(exposure: dict[str, dict], height: int = 330, fit: bool = False) -> go.Figure:
    """Proveedores en el mapa. exposure: {id: {"margin", "status", "label"(opcional), "hover"}}.
    Color = estado del margen, tamaño = gasto anual. Los no expuestos, en gris.
    fit=True encuadra la zona de los expuestos (simulador) en lugar del mapa entero."""
    sup = load_suppliers()
    max_spend = max(s.annual_spend_eur or 0 for s in sup.values()) or 1
    per_city: dict[str, int] = {}
    calm, hot = [], []
    for s in sup.values():
        ll = coords(s.city)
        if not ll:
            continue
        k = per_city.get(s.city, 0)
        per_city[s.city] = k + 1
        size = 8 + 24 * math.sqrt((s.annual_spend_eur or 0) / max_spend)
        p = {"lat": ll[0] + 0.35 * k, "lon": ll[1] + 0.45 * k, "size": size, "s": s}
        (hot if s.id in exposure else calm).append(p)
    fig = go.Figure()
    fig.add_trace(go.Scattergeo(
        lat=[p["lat"] for p in calm], lon=[p["lon"] for p in calm], mode="markers", showlegend=False,
        marker=dict(size=[p["size"] * .55 for p in calm], color=T.GREY_DOT, line=dict(width=0)),
        customdata=[[p["s"].id, f'{p["s"].name} · {CITY_ES.get(p["s"].city, p["s"].city)}'] for p in calm],
        hovertemplate="%{customdata[1]}<br>Sin exposición · pulsa para ver la ficha<extra></extra>"))
    hot.sort(key=lambda p: -p["size"])          # los grandes debajo
    colors = [STATUS_DOT[exposure[p["s"].id]["status"]][1] for p in hot]
    latent = [exposure[p["s"].id]["status"] == "riesgo_latente" for p in hot]
    fig.add_trace(go.Scattergeo(
        lat=[p["lat"] for p in hot], lon=[p["lon"] for p in hot], showlegend=False,
        mode="markers+text", text=[exposure[p["s"].id].get("label", "") for p in hot],
        textposition="middle right", textfont=dict(family="IBM Plex Sans", size=12, color=T.INK),
        marker=dict(size=[p["size"] for p in hot], color=colors, opacity=[.55 if x else .9 for x in latent],
                    line=dict(width=[2 if x else 2 for x in latent],
                              color=[T.AMBER if x else "#FFFFFF" for x in latent])),
        customdata=[[p["s"].id, p["s"].name, exposure[p["s"].id].get("hover", "")] for p in hot],
        hovertemplate="<b>%{customdata[1]}</b><br>%{customdata[2]}<br>Pulsa para ver la ficha<extra></extra>"))
    fig.update_geos(projection_type="natural earth", showland=True, landcolor="#DAD5E2", showocean=True,
                    oceancolor=T.BG, showcountries=False,
                    showcoastlines=False, showframe=False, showlakes=False, bgcolor=T.BG,
                    lataxis_range=[-8, 62], lonaxis_range=[-95, 142])
    if fit and hot:
        lats, lons = [p["lat"] for p in hot], [p["lon"] for p in hot]
        clat, clon = (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2
        hlat = max(12, (max(lats) - min(lats)) / 2 + 8)
        hlon = max(22, (max(lons) - min(lons)) / 2 + 14)
        fig.update_geos(lataxis_range=[clat - hlat, clat + hlat], lonaxis_range=[clon - hlon, clon + hlon])
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor=T.BG,
                      font=dict(family="IBM Plex Sans", color=T.INK),
                      hoverlabel=dict(font=dict(family="IBM Plex Sans"), bgcolor="#FFFFFF"))
    return fig


def map_label(supplier_id: str, margin: float, estimated: bool = False, no_stock: bool = False) -> str:
    from .data import signed
    name = short_supplier(load_suppliers()[supplier_id].name).split()[0]
    return f"{name} · sin stock" if no_stock else f"{name} · {signed(margin)} d{'*' if estimated else ''}"
