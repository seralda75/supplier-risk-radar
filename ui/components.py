"""Piezas HTML/CSS reutilizables (KPIs, tablas, leyendas) y el mapa de proveedores."""
from __future__ import annotations

import html
import math

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


def kpi(label: str, value: str, unit: str = "", sub: str = "", color: str = "", alert: bool = False,
        text: bool = False) -> str:
    """Indicador del mockup. text=True para valores que son palabras (un país), en la fuente normal."""
    style = f' style="color:{color}"' if color else ""
    u = f'<span class="u">{esc(unit)}</span>' if unit else ""
    cls = "txt" if text else "num"
    return (f'<div class="kpi{" alert" if alert else ""}"><span class="k">{esc(label)}</span>'
            f'<span class="v"><span class="{cls}"{style}>{esc(value)}</span>{u}</span>'
            f'<span class="s">{sub}</span></div>')


def kpis(items: list[str]) -> None:
    md('<section class="kpis" aria-label="Indicadores clave">' + "".join(items) + "</section>")


def table(headers: list[str], rows: list[list[str]], right: set[int] = frozenset()) -> str:
    """Tabla HTML con el estilo del panel. Las celdas ya vienen escapadas (pueden llevar HTML)."""
    th = "".join(f'<th class="{"r" if i in right else ""}">{esc(h)}</th>' for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(f'<td class="{"r" if i in right else ""}">{c}</td>' for i, c in enumerate(r))
                   + "</tr>" for r in rows)
    return f'<div class="tbl-wrap"><table class="tbl"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div>'


def card(title: str, body: str, note: str = "") -> str:
    n = f'<span class="sub">{note}</span>' if note else ""
    return f'<section class="card"><div class="card-head"><h2 class="h2">{esc(title)}</h2>{n}</div>{body}</section>'


def dot_legend(items: list[tuple[str, str]]) -> str:
    return ('<span class="legend">' + "".join(f'<span><span class="dot" style="background:{c}"></span>{esc(t)}</span>'
                                               for t, c in items) + "</span>")


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
        text=[f'{p["s"].name} · {CITY_ES.get(p["s"].city, p["s"].city)}' for p in calm],
        hovertemplate="%{text}<br>Sin exposición<extra></extra>"))
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
        customdata=[[p["s"].name, exposure[p["s"].id].get("hover", "")] for p in hot],
        hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>"))
    fig.update_geos(projection_type="natural earth", showland=True, landcolor="#DAD5E2", showocean=True,
                    oceancolor=T.BG, showcountries=True, countrycolor="#F4F3F7", countrywidth=.6,
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


def show_map(fig: go.Figure, key: str) -> None:
    # El contorno del mundo se sirve desde static/ (no desde cdn.plot.ly): funciona sin internet
    st.plotly_chart(fig, width="stretch", key=key,
                    config={"topojsonURL": "app/static/topojson/", "displaylogo": False, "displayModeBar": False})


def map_label(supplier_id: str, margin: float, estimated: bool = False, no_stock: bool = False) -> str:
    from .data import signed
    name = short_supplier(load_suppliers()[supplier_id].name).split()[0]
    return f"{name} · sin stock" if no_stock else f"{name} · {signed(margin)} d{'*' if estimated else ''}"
