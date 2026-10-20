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
from .components import esc, kpi, kpis, md, table
from .data import meur, pct
from .sheet import alt_text, vulnerability


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
    title.markdown('<div style="display:flex;flex-direction:column;gap:4px"><span class="overline">Vulnerabilidad '
                   'sin eventos</span><h1 class="h1">Proveedores</h1></div>', unsafe_allow_html=True)
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
                     f'style="width:140px"><div class="bar" style="width:{100 * spend / total / top_share:.0f}%">'
                     f'</div></div><span class="num">{pct(spend / total)}</span></div>',
                     f'<span class="num">{meur(spend)} M€</span>'])
    rest = countries[8:]
    rest_spend = sum(s.annual_spend_eur or 0 for c in rest for s in by_country[c])
    rows.append([f'<span class="muted">Otros {len(rest)} países</span>',
                 f'<span class="num">{sum(len(by_country[c]) for c in rest)}</span>',
                 f'<span class="num muted">{pct(rest_spend / total)}</span>',
                 f'<span class="num">{meur(rest_spend)} M€</span>'])
    country = ('<section class="card"><div class="card-head"><h2 class="h2">Concentración por país</h2>'
               '<span class="sub">% del gasto anual</span></div>'
               + table(["País", "Proveedores", "Peso en el gasto", "Gasto"], rows, right={1, 3}) + "</section>")
    zones = _zones()
    zrows = [[f"<strong>{esc(z)}</strong>",
              esc(", ".join(short_supplier(s.name) for s in ss)),
              f'<span class="num">{meur(sum(s.annual_spend_eur or 0 for s in ss))} M€</span>'] for z, ss in zones]
    zone = ('<section class="card"><div class="card-head"><h2 class="h2">Zonas con varios proveedores</h2>'
            '<span class="sub">Un solo evento (inundación, huelga portuaria, río sin navegación) los afecta a la '
            'vez</span></div>' + table(["Zona", "Proveedores", "Gasto"], zrows, right={2}) + "</section>")
    md(f'<div class="grid2">{country}{zone}</div>')

    rows = []
    for s in late:
        alt = sup[s.alternate_id]
        gap = alternate_margin(s, set()).lead_days - s.inventory_cover_days
        gap_txt = f"faltan {gap:.0f} d" if gap > 0 else "llega justo al agotarse"
        rows.append([f"<strong>{esc(s.name)}</strong><span class='w'>{esc(place_es(s.city, s.country))}</span>",
                     esc(material_es(s.material)),
                     f'<span class="num">{s.inventory_cover_days:.0f} d</span>',
                     esc(alt.name),
                     f'<span class="num">{alt.lead_time_days:.0f} d</span>',
                     f'<span style="color:{T.RED_INK}">{gap_txt}</span>'])
    md('<section class="card"><div class="card-head"><h2 class="h2">Alternativos que no llegan a tiempo</h2>'
       '<span class="sub">Si el proveedor se para, el stock se acaba antes de que llegue el primer envío del '
       'alternativo</span></div>'
       + table(["Proveedor", "Material", "Stock", "Alternativo", "Plazo del alternativo", "Diferencia"], rows,
               right={2, 4}) + "</section>")
    sheet.open_requested()


RANK_HEAD = ["#", "Proveedor", "Material", "Stock", "Alternativo", "Gasto anual", "Índice", ""]


def ranking(sup: dict) -> None:
    ranked = sorted(sup.values(), key=lambda s: (-vulnerability(s)[0], -(s.annual_spend_eur or 0)))[:10]
    with st.container(key="panel-ranking"):
        md('<div class="card-head"><h2 class="h2">Ranking de vulnerabilidad</h2>'
           '<span class="sub">Proveedor único, criticidad, días de stock y alternativo que no llega a tiempo · '
           'pulsa una fila para ver la ficha</span></div>'
           '<div class="rk head">' + "".join(f'<span class="{"r" if i in (3, 5) else ""}">{h}</span>'
                                              for i, h in enumerate(RANK_HEAD)) + "</div>")
        for i, s in enumerate(ranked, 1):
            score, _ = vulnerability(s)
            alt, ok = alt_text(s)
            stock = f"{s.inventory_cover_days:.0f} d" if s.inventory_cover_days is not None else "sin stock"
            with st.container(key=f"rk-{s.id}"):
                md(f'<div class="rk"><span class="num">{i}</span>'
                   f'<span><strong>{esc(s.name)}</strong><span class="w">{esc(place_es(s.city, s.country))}</span></span>'
                   f'<span>{esc(material_es(s.material))}</span><span class="num r">{stock}</span>'
                   f'<span style="color:{T.INK if ok else T.RED_INK}">{esc(alt)}</span>'
                   f'<span class="num r">{meur(s.annual_spend_eur or 0)} M€</span>'
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
    exposed = {c.supplier_id for a in cache.alerts("test") for c in [a.worst] + a.others}
    ids = sorted(sup, key=lambda i: (i not in exposed, sup[i].name))
    st.selectbox("Ficha de proveedor", ids, index=None, key="sup_pick", on_change=_pick,
                 placeholder="Buscar un proveedor y abrir su ficha…", label_visibility="collapsed",
                 format_func=lambda i: f"{sup[i].name} · {place_es(sup[i].city, sup[i].country)}"
                                       + ("  · en riesgo" if i in exposed else ""))
