"""Proveedores: dónde es vulnerable Helixa aunque no haya ninguna noticia (CLAUDE.md, 8.2).

Ranking de vulnerabilidad (la misma puntuación de dependencia que decide la urgencia), gasto en
proveedores únicos, concentración por país y por zona, alternativos que no llegan a tiempo y ficha.
"""
from __future__ import annotations

from collections import defaultdict

import streamlit as st

from core import feedback, results
from core.countdown import alternate_margin
from core.labels import (CATEGORY_ES, CITY_ES, COUNTRY_ES, CRITICALITY_ES, ZONE_ES, material_es, place_es,
                         product_es, short_supplier)
from core.schemas import EVENT_LABELS_ES
from core.suppliers import load_suppliers
from core.urgency import dependency

from . import theme as T
from .components import esc, kpi, kpis, md, table
from .data import build_alerts, meur, pct, signed, status_chip

SPLIT_ES = {"test": "Test", "validation": "Validación", "train": "Entrenamiento"}


LATE_ALTERNATE = 0.2     # suma al índice si el alternativo no llega antes de que se acabe el stock


def vulnerability(s) -> tuple[float, list[str]]:
    """Índice de vulnerabilidad sin eventos (CLAUDE.md, 8.2): la dependencia que decide la urgencia
    (único, criticidad, días de stock) + 0,2 si el alternativo aprobado no llega a tiempo."""
    d = dependency(s)
    score, factors = d.score, list(d.factors)
    if s.alternate_id and s.inventory_cover_days is not None and not alternate_margin(s, set()).in_time:
        score += LATE_ALTERNATE
        factors.append("el alternativo no llega a tiempo")
    return round(min(score, 1.0), 2), factors


def _alt_text(s) -> tuple[str, bool]:
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


def render(loaded: dict) -> None:
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

    md('<div style="display:flex;flex-direction:column;gap:4px"><span class="overline">Vulnerabilidad sin eventos'
       '</span><h1 class="h1">Proveedores</h1></div>')
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

    # Ranking de vulnerabilidad
    ranked = sorted(sup.values(), key=lambda s: (-vulnerability(s)[0], -(s.annual_spend_eur or 0)))[:10]
    rows = []
    for i, s in enumerate(ranked, 1):
        score, _ = vulnerability(s)
        alt, ok = _alt_text(s)
        stock = f'{s.inventory_cover_days:.0f} d' if s.inventory_cover_days is not None else "sin stock"
        rows.append([f'<span class="num">{i}</span>',
                     f"<strong>{esc(s.name)}</strong><span class='w'>{esc(place_es(s.city, s.country))}</span>",
                     esc(material_es(s.material)), f'<span class="num">{stock}</span>',
                     f'<span style="color:{T.INK if ok else T.RED_INK}">{esc(alt)}</span>',
                     f'<span class="num">{meur(s.annual_spend_eur or 0)} M€</span>',
                     f'<div style="display:flex;align-items:center;gap:8px"><div class="bar-bg" style="width:90px">'
                     f'<div class="bar" style="width:{score * 100:.0f}%"></div></div>'
                     f'<span class="num">{score:.2f}</span></div>'])
    md('<section class="card"><div class="card-head"><h2 class="h2">Ranking de vulnerabilidad</h2>'
       '<span class="sub">Proveedor único, criticidad, días de stock y alternativo que no llega a tiempo'
       '</span></div>' + table(["#", "Proveedor", "Material", "Stock", "Alternativo", "Gasto anual", "Índice"], rows,
                               right={3, 5}) + "</section>")

    left, right = st.columns([7, 5], gap="medium")
    with left:
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
        md('<section class="card"><div class="card-head"><h2 class="h2">Concentración por país</h2>'
           '<span class="sub">% del gasto anual</span></div>'
           + table(["País", "Proveedores", "Peso en el gasto", "Gasto"], rows, right={1, 3}) + "</section>")
    with right:
        rows = []
        for s in late:
            alt = sup[s.alternate_id]
            gap = alternate_margin(s, set()).lead_days - s.inventory_cover_days
            gap_txt = f"faltan {gap:.0f} d" if gap > 0 else "llega justo al agotarse"
            rows.append([f"<strong>{esc(s.name)}</strong><span class='w'>{esc(material_es(s.material))}</span>",
                         f'<span class="num">{s.inventory_cover_days:.0f} d</span>',
                         f"{esc(short_supplier(alt.name))}<span class='w'>tarda {alt.lead_time_days:.0f} d · "
                         f"{gap_txt}</span>"])
        md('<section class="card"><div class="card-head"><h2 class="h2">Alternativos que no llegan a tiempo</h2></div>'
           '<span class="sub">Si el proveedor se para, el stock se acaba antes de que llegue el primer envío del '
           'alternativo.</span>' + table(["Proveedor", "Stock", "Alternativo"], rows, right={1}) + "</section>")
        zones = _zones()
        zrows = [[f"<strong>{esc(z)}</strong>",
                  esc(", ".join(short_supplier(s.name) for s in ss)),
                  f'<span class="num">{meur(sum(s.annual_spend_eur or 0 for s in ss))} M€</span>'] for z, ss in zones]
        md('<section class="card"><div class="card-head"><h2 class="h2">Zonas con varios proveedores</h2></div>'
           '<span class="sub">Un solo evento (inundación, huelga portuaria, río sin navegación) los afecta a la vez.'
           '</span>' + table(["Zona", "Proveedores", "Gasto"], zrows, right={2}) + "</section>")

    _sheet(loaded)


def _sheet(loaded: dict) -> None:
    sup = load_suppliers()
    alerts_by_split = {sp: build_alerts(d["results"]) for sp, d in loaded.items() if d}
    exposed = {c.supplier_id for a in alerts_by_split.get("test", []) for c in [a.worst] + a.others}
    ids = sorted(sup, key=lambda i: (i not in exposed, sup[i].name))
    with st.container(key="panel-sheet"):
        md('<div class="card-head"><h2 class="h2">Ficha de proveedor</h2>'
           '<span class="sub">Primero, los expuestos en las noticias de test</span></div>')
        sid = st.selectbox("Proveedor", ids, key="sup_sel", label_visibility="collapsed",
                           format_func=lambda i: f"{sup[i].name} · {place_es(sup[i].city, sup[i].country)}"
                                                 + ("  · en riesgo" if i in exposed else ""))
        s = sup[sid]
        score, _ = vulnerability(s)
        alt, ok = _alt_text(s)
        chips = [f'<span class="chip purple">{esc(CATEGORY_ES.get(s.category, s.category))}</span>',
                 '<span class="chip red">Proveedor único</span>' if s.single_source else
                 '<span class="chip green">Con alternativo</span>',
                 f'<span class="chip grey">Criticidad {CRITICALITY_ES.get(s.criticality, s.criticality)}</span>']
        stock = f"{s.inventory_cover_days:.0f} días" if s.inventory_cover_days is not None else "sin stock"
        lead = f"{s.lead_time_days:.0f} días" if s.lead_time_days is not None else "—"
        md(f'<div style="display:flex;flex-direction:column;gap:6px"><h2 class="det-name">{esc(s.name)}</h2>'
           f'<span class="det-sub">{esc(place_es(s.city, s.country))} · {esc(material_es(s.material))}</span>'
           f'<span style="display:flex;gap:8px;flex-wrap:wrap">{"".join(chips)}</span></div>')
        md(f'<div class="boxes"><div class="box"><span class="l">Stock de seguridad</span><span class="num v">{stock}'
           f'</span><span class="s">cobertura de inventario</span></div>'
           f'<div class="box"><span class="l">Plazo de entrega</span><span class="num v">{lead}</span>'
           f'<span class="s">desde el pedido</span></div>'
           f'<div class="box"><span class="l">Gasto anual</span><span class="num v">{meur(s.annual_spend_eur or 0)} M€'
           f'</span><span class="s">{s.share_of_category_pct or 0:.0f} % de su categoría</span></div>'
           f'<div class="box {"" if ok else "amber"}"><span class="l">Alternativo</span><span class="t" '
           f'style="font-size:16px">{esc(alt)}</span><span class="s">índice de vulnerabilidad {score:.2f}</span></div>'
           '</div>')
        prods = ", ".join(product_es(p) for p in s.products) or "ninguno registrado"
        need = f" · necesidad mensual {s.monthly_requirement}" if s.monthly_requirement else ""
        md(f'<p class="what" style="font-size:15px"><strong>Medicamentos que dependen de él:</strong> {esc(prods)}'
           f'{esc(need)}</p>')
        rows = []
        for sp, alerts in alerts_by_split.items():
            fb = feedback.latest(sp)
            for r in loaded[sp]["results"]:
                if sid not in r["affected_ids"]:
                    continue
                a = next((x for x in alerts if x.id == r["news_id"]), None)
                c = next((x for x in r.get("countdown", []) if x["supplier_id"] == sid), None)
                if a:
                    text, color = status_chip(a)
                    state = f'<span class="chip {color}">{esc(text)}</span>'
                else:
                    state = '<span class="chip grey">Sin riesgo</span>'
                margin = (f'<span class="num">{signed(c["margin_days"])} d</span>'
                          if c and c["inventory_days"] is not None else "—")
                rows.append([f'<span class="num">{esc((r.get("published_date") or "")[:10])}</span>',
                             f"{esc(r['headline'])}<span class='w'>{SPLIT_ES[sp]} · {esc(r['news_id'])} · "
                             f"{esc(EVENT_LABELS_ES.get(r['event_type'], r['event_type']))}</span>",
                             state, margin,
                             esc(feedback.VERDICTS[fb[r["news_id"]]["verdict"]]) if r["news_id"] in fb else "—"])
        rows.sort(key=lambda x: x[0], reverse=True)
        md('<h3 class="h3">Historial de eventos</h3>' + (
            table(["Fecha", "Noticia", "Estado", "Margen", "Decisión"], rows, right={3}) if rows else
            '<p class="sub">Ninguna noticia de los tres conjuntos menciona a este proveedor.</p>'))
