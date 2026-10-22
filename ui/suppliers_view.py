"""Proveedores: dónde es vulnerable Helixa aunque no haya ninguna noticia (CLAUDE.md, 8.2).

Cuadrícula sin huecos: KPIs · ranking de vulnerabilidad (a todo el ancho) · concentración por país y zonas
con varios proveedores (dos tarjetas de la misma altura) · alternativos que no llegan a tiempo (a todo el
ancho). La ficha de proveedor (ui/sheet.py) se abre en una ventana: desde el ranking o desde el buscador
de la cabecera.
"""
from __future__ import annotations

from collections import defaultdict

import streamlit as st

from core.countdown import alternate_margin
from core.labels import CITY_ES, COUNTRY_ES, ZONE_ES, material_es, place_es, short_supplier
from core.suppliers import load_suppliers

from . import cache, sheet
from . import theme as T
from .components import card, esc, head, kpi, kpis, md, table, tip
from .data import meur, pct
from .sheet import vulnerability


def _zones() -> list[tuple[str, list]]:
    """Regiones, ríos y puertos compartidos por varios proveedores: un solo evento los afecta a la vez."""
    sup = load_suppliers()
    by: dict[str, list] = defaultdict(list)
    for s in sup.values():
        for z in s.geo.get("regions", [])[:1] + s.geo.get("rivers", []):
            by[ZONE_ES.get(z, z)].append(s)
        if s.geo.get("port"):
            by[f"Puerto de {CITY_ES.get(s.city, s.city)}"].append(s)
    out = [(z, ss) for z, ss in by.items() if len({x.city for x in ss}) >= 2 or (z.startswith("Puerto") and len(ss) >= 2)]
    return sorted(out, key=lambda x: -sum(s.annual_spend_eur or 0 for s in x[1]))


def render() -> None:
    sup = load_suppliers()
    total = sum(s.annual_spend_eur or 0 for s in sup.values())
    unique = [s for s in sup.values() if s.single_source]
    late = [s for s in sup.values() if s.alternate_id and s.inventory_cover_days is not None
            and not alternate_margin(s, set()).in_time]
    by_country: dict[str, list] = defaultdict(list)
    for s in sup.values():
        by_country[s.country].append(s)
    top_country = max(by_country, key=lambda c: sum(s.annual_spend_eur or 0 for s in by_country[c]))
    top_share = sum(s.annual_spend_eur or 0 for s in by_country[top_country]) / total

    title, search = st.columns([3, 1.4], vertical_alignment="bottom")
    title.markdown(f'<h1 class="h1">Proveedores{tip("Dónde es vulnerable Helixa aunque no haya noticias")}</h1>',
                   unsafe_allow_html=True)
    with search:
        _search(sup)
    spend_unique = sum(s.annual_spend_eur or 0 for s in unique)
    kpis([
        kpi("Gasto en proveedores únicos", f"{spend_unique / total * 100:.0f}", unit="%",
            sub=f"{meur(spend_unique)} M€ de {meur(total)} M€"),
        kpi("Proveedores únicos", str(len(unique)), unit=f"de {len(sup)}", sub="sin alternativo aprobado"),
        kpi("Alternativos que no llegan", str(len(late)), color=T.AMBER if late else "",
            sub="tardan más que el stock que cubren"),
        kpi("País con más gasto", COUNTRY_ES.get(top_country, top_country), text=True,
            sub=f"{pct(top_share)} del gasto total"),
    ])

    ranking(sup)

    # Concentración por país | zonas con varios proveedores: una fila de dos tarjetas de la misma altura
    rows = []
    countries = sorted(by_country, key=lambda c: -sum(s.annual_spend_eur or 0 for s in by_country[c]))
    for c in countries[:8]:
        ss = by_country[c]
        spend = sum(s.annual_spend_eur or 0 for s in ss)
        uniq = sum(s.single_source for s in ss)
        rows.append([f"<strong>{esc(COUNTRY_ES.get(c, c))}</strong>",
                     f'<span class="num">{len(ss)}</span>' + (f'<span class="w">{uniq} único(s)</span>' if uniq else ""),
                     f'<div style="display:flex;align-items:center;gap:8px"><div class="bar-bg" '
                     f'style="width:96px"><div class="bar" style="width:{100 * spend / total / top_share:.0f}%">'
                     f'</div></div><span class="num">{pct(spend / total)}</span></div>'])
    rest = countries[8:]
    rest_spend = sum(s.annual_spend_eur or 0 for c in rest for s in by_country[c])
    rows.append([f'<span class="muted">Otros {len(rest)} países</span>',
                 f'<span class="num">{sum(len(by_country[c]) for c in rest)}</span>',
                 f'<span class="num muted">{pct(rest_spend / total)}</span>'])
    country = card("Concentración por país", table(["País", "Proveedores", "Peso en el gasto"], rows, right={1}),
                   "% del gasto anual")
    zones = _zones()
    zrows = [[f"<strong>{esc(z)}</strong>",
              esc(", ".join(short_supplier(s.name) for s in ss)),
              f'<span class="num">{meur(sum(s.annual_spend_eur or 0 for s in ss))} M€</span>'] for z, ss in zones]
    zone = card("Zonas con varios proveedores", table(["Zona", "Proveedores", "Gasto"], zrows, right={2}),
                "Un solo evento (inundación, huelga portuaria, río sin navegación) los afecta a la vez")
    md(f'<div class="grid2">{country}{zone}</div>')

    rows = []
    for s in late:
        alt = sup[s.alternate_id]
        gap = alternate_margin(s, set()).lead_days - s.inventory_cover_days
        gap_txt = f"faltan {gap:.0f} d" if gap > 0 else "llega justo"
        rows.append([f"<strong>{esc(s.name)}</strong><span class='w'>{esc(place_es(s.city, s.country))}</span>",
                     esc(alt.name),
                     f'<span style="color:{T.RED_INK}">{gap_txt}</span>'])
    md(card("Alternativos que no llegan", table(["Proveedor", "Alternativo", "Diferencia"], rows),
            "Si el proveedor se para, el stock se acaba antes de que llegue el primer envío del alternativo"))
    sheet.open_requested()


RANK_HEAD = ["#", "Proveedor", "Stock", "Índice", ""]


def ranking(sup: dict) -> None:
    ranked = sorted(sup.values(), key=lambda s: (-vulnerability(s)[0], -(s.annual_spend_eur or 0)))[:10]
    with st.container(key="panel-ranking"):
        md(head("Ranking de vulnerabilidad", "Proveedor único, criticidad, días de stock y alternativo que no "
                "llega a tiempo. Pulsa una fila para ver la ficha."))
        md('<div class="rk head">' + "".join(f'<span class="{"r" if i == 2 else ""}">{h}</span>'
                                              for i, h in enumerate(RANK_HEAD)) + "</div>")
        for i, s in enumerate(ranked, 1):
            score, _ = vulnerability(s)
            stock = f"{s.inventory_cover_days:.0f} d" if s.inventory_cover_days is not None else "sin stock"
            with st.container(key=f"rk-{s.id}"):
                md(f'<div class="rk"><span class="num">{i}</span>'
                   f'<span><strong>{esc(s.name)}</strong><span class="w">{esc(place_es(s.city, s.country))}</span></span>'
                   f'<span class="num r">{stock}</span>'
                   f'<span style="display:flex;align-items:center;gap:8px"><span class="bar-bg" style="width:90px">'
                   f'<span class="bar" style="display:block;width:{score * 100:.0f}%"></span></span>'
                   f'<span class="num">{score:.2f}</span></span><span class="go" aria-hidden="true">›</span></div>')
                st.button(f"Ficha de {s.name}", key=f"rkbtn-{s.id}", on_click=sheet.request, args=(s.id,))


def _pick() -> None:
    """Buscador: abre la ficha elegida en una ventana y deja el buscador vacío para la próxima."""
    sid = st.session_state.get("sup_pick")
    if sid:
        sheet.request(sid)
    st.session_state["sup_pick"] = None


def _search(sup: dict) -> None:
    exposed = {c.supplier_id for a in cache.alerts(cache.split()) for c in [a.worst] + a.others}
    ids = sorted(sup, key=lambda i: (i not in exposed, sup[i].name))
    st.selectbox("Ficha de proveedor", ids, index=None, key="sup_pick", on_change=_pick,
                 placeholder="Buscar un proveedor y abrir su ficha…", label_visibility="collapsed",
                 format_func=lambda i: f"{sup[i].name} · {place_es(sup[i].city, sup[i].country)}"
                                       + ("  · en riesgo" if i in exposed else ""))
