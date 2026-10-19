"""Simulador «¿Y si…?» (fase 5) con el estilo del centro de control.

El LLM solo traduce la pregunta a un escenario estructurado; el usuario lo revisa en un formulario y el
código calcula el impacto (core/scenario.py). Sin Ollama funciona con los ejemplos precalculados.
"""
from __future__ import annotations

import streamlit as st

from core import scenario
from core.actions import plan_steps
from core.labels import CATEGORY_ES, material_es, place_es, product_es, short_supplier
from core.schemas import EVENT_LABELS_ES
from core.suppliers import CITY_GEO, COUNTRY_ALIASES, MATERIAL_ALIASES, SUPPLIER_ROUTES, load_suppliers

from . import theme as T
from .components import STATUS_DOT, dot_legend, esc, kpi, kpis, map_label, md, risk_map, show_map, table
from .data import meur, pct, signed

SC_REGIONS = sorted({x for g in CITY_GEO.values() for x in g.get("regions", []) + g.get("rivers", [])}
                    | {x for routes in SUPPLIER_ROUTES.values() for x in routes})
SC_CITIES = sorted(CITY_GEO)
SC_COUNTRIES = sorted(COUNTRY_ALIASES)


def load_scenario(sc: scenario.Scenario, source: str, dropped: list[str]) -> None:
    """Carga un escenario en el formulario (sustituye al anterior y borra el cálculo previo)."""
    st.session_state["sc_loaded"] = {"scenario": sc.model_dump(), "source": source, "dropped": dropped}
    st.session_state["sc_ver"] = st.session_state.get("sc_ver", 0) + 1
    st.session_state.pop("sc_calc", None)
    st.session_state.pop("sc_error", None)


def use_example(examples: list[dict]) -> None:
    ex = examples[st.session_state["sc_example"]]
    load_scenario(ex["scenario"], f"Ejemplo precalculado: «{ex['text']}»", ex["dropped"])


def run_interpret() -> None:
    text = st.session_state.get("sc_text", "").strip()
    try:
        sc, dropped = scenario.interpret(text)
    except Exception as e:                      # Ollama caído, tiempo de espera, JSON no válido...
        st.session_state["sc_error"] = f"No se pudo interpretar el escenario: {e}"
        return
    load_scenario(sc, f"Interpretado por la IA a partir de: «{text}»", dropped)


def _with_extra(options: list[str], current: list[str]) -> list[str]:
    return options + [x for x in current if x not in options]


def _form(loaded: dict) -> None:
    sc0 = scenario.Scenario.model_validate(loaded["scenario"])
    with st.form(f"sc_form_{st.session_state.get('sc_ver', 0)}", border=False):
        md('<div class="card-head"><h2 class="h2">Escenario interpretado</h2>'
           '<span class="sub">Revísalo y corrígelo antes de calcular</span></div>')
        md(f'<span class="sub">{esc(loaded["source"])}</span>')
        if loaded["dropped"]:
            md(f'<span class="sub">Descartado porque no aparece en el texto: {esc(", ".join(loaded["dropped"]))}.</span>')
        c1, c2, c3 = st.columns([1.6, 1.2, .8])
        title = c1.text_input("Título", sc0.title)
        events = list(scenario.SCENARIO_EVENTS)
        event = c2.selectbox("Tipo de evento", events, index=events.index(sc0.event_type),
                             format_func=lambda e: EVENT_LABELS_ES.get(e, e).capitalize())
        dur = c3.number_input("Duración (días)", min_value=0, max_value=730, step=1, value=int(sc0.duration_days or 0),
                              help="0 = sin indicar: se usa una duración típica del tipo de evento (estimada)")
        c1, c2, c3 = st.columns(3)
        countries = c1.multiselect("Países", _with_extra(SC_COUNTRIES, sc0.countries), sc0.countries,
                                   accept_new_options=True, placeholder="Elige o escribe…")
        regions = c2.multiselect("Regiones, ríos y rutas", _with_extra(SC_REGIONS, sc0.regions), sc0.regions,
                                 accept_new_options=True, placeholder="Elige o escribe…")
        cities = c3.multiselect("Ciudades y puertos", _with_extra(SC_CITIES, sc0.cities), sc0.cities,
                                accept_new_options=True, placeholder="Elige o escribe…")
        c1, c2 = st.columns(2, gap="medium")
        categories = c1.multiselect("Solo estas categorías (vacío = todas)", list(scenario.CATEGORIES),
                                    sc0.categories, placeholder="Todas",
                                    format_func=lambda c: CATEGORY_ES.get(c, c))
        materials = c2.multiselect("Solo estos materiales (vacío = todos)", list(MATERIAL_ALIASES), sc0.materials,
                                   placeholder="Todos", format_func=lambda m: material_es(m).capitalize())
        if st.form_submit_button("Calcular impacto", type="primary"):
            st.session_state["sc_calc"] = scenario.Scenario(
                title=title, event_type=event, countries=countries, regions=regions, cities=cities,
                categories=categories, materials=materials, duration_value=dur or None,
                duration_unit="days" if dur else None).model_dump()


def _result(imp: scenario.ScenarioImpact) -> None:
    sc, sup = imp.scenario, load_suppliers()
    dur = (f"{sc.duration_days} días" if sc.duration_days is not None else
           "duración típica del evento (estimada)")
    scope = ", ".join(sc.places) or "todo el mundo"
    filt = ", ".join([CATEGORY_ES.get(c, c) for c in sc.categories] + [material_es(m) for m in sc.materials])
    md(f'<div style="display:flex;flex-direction:column;gap:4px"><span class="overline">Resultado del escenario</span>'
       f'<h2 class="det-name">{esc(sc.title)}</h2><span class="det-sub">'
       f'{esc(EVENT_LABELS_ES.get(sc.event_type, sc.event_type).capitalize())} · {esc(dur)} · {esc(scope)}'
       f'{" · solo " + esc(filt) if filt else ""}</span></div>')
    warn = []
    if imp.note:
        warn.append(imp.note)
    if imp.unmatched_places:
        warn.append("Sin proveedores de Helixa (o nombre no reconocido): " + ", ".join(imp.unmatched_places) + ".")
    if imp.excluded:
        warn.append("En la zona pero fuera del escenario: "
                    + ", ".join(short_supplier(sup[i].name) for i in imp.excluded) + ".")
    if warn:
        md('<div class="trust">' + "".join(f"<span>{T.ICON_WARN}{esc(w)}</span>" for w in warn) + "</div>")
    if not imp.hits:
        md('<section class="card"><p class="what">Ningún proveedor de Helixa queda afectado por este escenario.'
           '</p></section>')
        return

    cds = {c.supplier_id: c for c in imp.countdowns}
    mats, prods = imp.materials_table(), imp.products_table()
    total = sum(s.annual_spend_eur or 0 for s in sup.values())
    with_stock = [c for c in imp.countdowns if c.inventory_days is not None]
    low = min(with_stock, key=lambda c: c.margin_days) if with_stock else None
    deficit = [c for c in imp.countdowns if c.deficit_days > 0]
    kpis([
        kpi("Proveedores afectados", str(len(imp.hits)), unit=f"de {len(sup)}",
            sub=f"{sum(h.supplier.single_source for h in imp.hits)} proveedor(es) único(s)"),
        kpi("Con rotura prevista", str(len(deficit)), color=T.RED if deficit else "",
            sub="se quedan sin suministro antes de recuperarse"),
        kpi("Medicamentos afectados", str(len(prods)),
            sub=esc(" · ".join(p["product"].split()[0] for p in prods)) or "ninguno"),
        kpi("Gasto anual expuesto", meur(imp.spend_exposed), unit="M€",
            sub=f"{pct(imp.spend_exposed / total)} del gasto total · {meur(imp.spend_at_risk)} M€ con rotura"),
        kpi("Menor margen", signed(low.margin_days) if low else "—", unit="días" if low else "",
            color=T.RED if low and low.margin_days < 0 else "", alert=bool(low and low.margin_days < 0),
            sub=esc(short_supplier(sup[low.supplier_id].name)) if low else "sin proveedores con stock"),
    ])

    left, right = st.columns([7, 5], gap="medium")
    with left:
        rows = []
        for h in sorted(imp.hits, key=lambda h: (cds[h.supplier.id].inventory_days is None,
                                                 cds[h.supplier.id].margin_days)):
            s, c = h.supplier, cds[h.supplier.id]
            label, color = STATUS_DOT[c.status]
            margin = (f'<span class="num" style="color:{color};font-weight:600">{signed(c.margin_days)} d</span>'
                      if c.inventory_days is not None else '<span class="sub">sin stock</span>')
            est = '<span class="w">estimado</span>' if c.ttr_estimated else ""
            rows.append([f"<strong>{esc(s.name)}</strong><span class='w'>{esc(place_es(s.city, s.country))} · "
                         f"{esc(material_es(s.material))}</span>", margin + est,
                         f'<span class="num">{c.deficit_days:.0f} d</span>' if c.deficit_days else "—",
                         f'<span class="chip" style="color:{color};background:{T.BG}">{esc(label)}</span>',
                         f'<span class="num">{meur(s.annual_spend_eur or 0)} M€</span>'])
        md('<section class="card"><div class="card-head"><h2 class="h2">Proveedores afectados</h2>'
           '<span class="sub">Ordenado por días de margen</span></div>'
           + table(["Proveedor", "Días de margen", "Días sin suministro", "Estado", "Gasto anual"], rows,
                   right={1, 2, 4}) + "</section>")
    with right:
        exposure = {h.supplier.id: {"margin": cds[h.supplier.id].margin_days, "status": cds[h.supplier.id].status,
                                    "label": map_label(h.supplier.id, cds[h.supplier.id].margin_days,
                                                     no_stock=cds[h.supplier.id].inventory_days is None),
                                    "hover": "; ".join(h.reasons)} for h in imp.hits}
        with st.container(key="panel-simmap"):
            md('<div class="card-head"><h2 class="h2">Dónde golpea</h2><span class="sub">Tamaño = gasto anual</span>'
               '</div>')
            show_map(risk_map(exposure, fit=True), key="map-sim")
            present = [s for s in STATUS_DOT if any(e["status"] == s for e in exposure.values())]
            md(dot_legend([STATUS_DOT[s] for s in present] + [("Fuera del escenario", T.GREY_DOT)]))

    left, right = st.columns(2, gap="medium")
    with left:
        rows = [[esc(material_es(m["material"]).capitalize()),
                 esc(short_supplier(sup[m["primary"]].name)) + (" ⚠" if m["primary_hit"] else ""),
                 (esc(short_supplier(sup[m["alternate"]].name)) + (" ⚠" if m["alternate_hit"] else ""))
                 if m["alternate"] else "—",
                 f'<span class="num" style="color:{STATUS_DOT[m["status"]][1]};font-weight:600">'
                 f'{signed(m["margin"])} d</span>'] for m in mats]
        md(f'<section class="card"><div class="card-head"><h2 class="h2">Materiales</h2>'
           f'<span class="sub">⚠ = afectado</span></div>'
           + table(["Material", "Principal", "Alternativo", "Peor margen"], rows, right={3}) + "</section>")
    with right:
        rows = [[f"<strong>{esc(product_es(p['product']))}</strong>",
                 esc(", ".join(material_es(m) for m in p["materials"])),
                 f'<span class="num" style="color:{STATUS_DOT[p["status"]][1]};font-weight:600">'
                 f'{signed(p["margin"])} d</span>'] for p in prods]
        md('<section class="card"><div class="card-head"><h2 class="h2">Medicamentos</h2>'
           '<span class="sub">Peor margen de sus materiales</span></div>'
           + table(["Medicamento", "Materiales afectados", "Peor margen"], rows, right={2}) + "</section>")

    blocks = []
    for c in sorted(imp.countdowns, key=lambda c: (c.inventory_days is None, c.margin_days)):
        s = sup[c.supplier_id]
        steps = plan_steps(c, s, urgent=c.deficit_days > 0)
        blocks.append(f'<div style="display:flex;flex-direction:column;gap:8px"><span style="font-weight:700">'
                      f'{esc(s.name)} <span class="sub" style="font-weight:400">· {esc(place_es(s.city, s.country))}'
                      f'</span></span><ol class="steps">' + "".join(
                          f'<li><span class="num i">{i}</span><span class="b"><span class="x">{esc(x.text)}</span>'
                          f'<span class="o">{esc(x.owner)} · {esc(x.when)}</span></span></li>'
                          for i, x in enumerate(steps, 1)) + "</ol></div>")
    md('<section class="card" style="gap:18px"><div class="card-head"><h2 class="h2">Plan recomendado</h2>'
       '<span class="sub">Del menor margen al mayor</span></div>' + "".join(blocks)
       + '<span class="sub">Logística y servicios no tienen stock: el impacto es inmediato durante toda la '
         'duración, aunque exista un alternativo.</span></section>')


def render(llm_up: bool) -> None:
    examples = scenario.load_examples()
    md('<div style="display:flex;flex-direction:column;gap:4px"><span class="overline">Escenarios</span>'
       '<h1 class="h1">Simulador «¿Y si…?»</h1></div>')
    with st.container(key="panel-siminput"):
        md('<div class="card-head"><h2 class="h2">¿Qué pasaría si…?</h2><span class="sub">La IA solo traduce tu '
           'pregunta; los proveedores, los márgenes y el plan los calcula el sistema con los datos de Helixa'
           '</span></div>')
        left, right = st.columns([1.3, 1], vertical_alignment="bottom")
        with left:
            st.text_area("Escribe un escenario", key="sc_text", height=90, disabled=not llm_up,
                         placeholder="¿Y si se inunda Gujarat 3 semanas?")
        with right:
            if examples:
                st.selectbox("…o elige un ejemplo", range(len(examples)), key="sc_example",
                             format_func=lambda i: examples[i]["text"])
        b1, b2, _ = st.columns([1, 1, 2.2])
        b1.button("Interpretar con la IA", on_click=run_interpret, disabled=not llm_up, type="primary",
                  key="sc_interpret", width="stretch")
        if examples:
            b2.button("Usar este ejemplo", on_click=use_example, args=(examples,), key="sc_use_example",
                      width="stretch")
        if not llm_up:
            md(f'<div class="trust"><span>{T.ICON_WARN}La IA local no está disponible: usa los ejemplos (ya '
               'interpretados). Puedes corregirlos; el cálculo no necesita la IA.</span></div>')
        if not examples:
            md('<span class="sub">No hay ejemplos precalculados: python scripts/build_scenarios.py</span>')
        if st.session_state.get("sc_error"):
            st.error(st.session_state["sc_error"])

    loaded = st.session_state.get("sc_loaded")
    if loaded:
        with st.container(key="panel-simform"):
            _form(loaded)
    calc = st.session_state.get("sc_calc")
    if calc:
        _result(scenario.simulate(scenario.Scenario.model_validate(calc)))
