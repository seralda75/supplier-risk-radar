"""Simulador «¿Y si…?» (fase 5) con el estilo del centro de control, en tres pasos: Escenario → Revisa → Impacto.

El LLM solo traduce la pregunta a un escenario estructurado; el usuario lo revisa en un formulario y el
código calcula el impacto (core/scenario.py). Sin Ollama funciona con los ejemplos precalculados.
Cada paso aparece cuando se completa el anterior.
"""
from __future__ import annotations

import streamlit as st

from core import scenario
from core.actions import plan_steps
from core.labels import material_es, short_supplier
from core.schemas import EVENT_LABELS_ES
from core.suppliers import CITY_GEO, COUNTRY_ALIASES, MATERIAL_ALIASES, SUPPLIER_ROUTES, load_suppliers

from . import cache, sheet
from . import theme as T
from .components import STATUS_DOT, dot_legend, esc, head, kpi, kpis, map_label, md, risk_map, tip
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


def use_example(examples: list[dict], i: int) -> None:
    ex = examples[i]
    if cache.llm_up():                           # con la IA activa, el ejemplo también rellena la caja
        st.session_state["sc_text"] = ex["text"]
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


def _split_places(chosen: list[str], sc0: scenario.Scenario) -> tuple[list[str], list[str], list[str]]:
    """Reparte los lugares del formulario en países, regiones y ciudades (conserva la clase que ya tenían)."""
    countries, regions, cities = [], [], []
    for x in chosen:
        if x in sc0.countries or (x in SC_COUNTRIES and x not in sc0.regions + sc0.cities):
            countries.append(x)
        elif x in sc0.cities or (x in SC_CITIES and x not in sc0.regions):
            cities.append(x)
        else:
            regions.append(x)
    return countries, regions, cities


def _stepper(step: int) -> None:
    """Indicador 1 → 2 → 3: hecho, actual o pendiente."""
    names = ["Escenario", "Revisa", "Impacto"]
    md('<ol class="sc-steps">' + "".join(
        f'<li class="{"done" if i < step else "on" if i == step else ""}"><span class="n">'
        f'{"✓" if i < step else i}</span>{n}</li>' for i, n in enumerate(names, 1)) + "</ol>")


def _form(loaded: dict) -> None:
    """Paso 2: el escenario interpretado en un formulario compacto de dos columnas."""
    sc0 = scenario.Scenario.model_validate(loaded["scenario"])
    places0 = sc0.countries + sc0.regions + sc0.cities
    with st.form(f"sc_form_{st.session_state.get('sc_ver', 0)}", border=False):
        extra = f". Descartado (no está en el texto): {', '.join(loaded['dropped'])}" if loaded["dropped"] else ""
        md(head(sc0.title or "Escenario", f"Revísalo y corrígelo antes de calcular. {loaded['source']}{extra}"))
        c1, c2 = st.columns(2, gap="medium")
        events = list(scenario.SCENARIO_EVENTS)
        event = c1.selectbox("Tipo de evento", events, index=events.index(sc0.event_type),
                             format_func=lambda e: EVENT_LABELS_ES.get(e, e).capitalize())
        places = c2.multiselect("Lugares", _with_extra(SC_COUNTRIES + SC_REGIONS + SC_CITIES, places0), places0,
                                accept_new_options=True, placeholder="Elige o escribe…")
        materials = c1.multiselect("Materiales (vacío = todos)", list(MATERIAL_ALIASES), sc0.materials,
                                   placeholder="Todos", format_func=lambda m: material_es(m).capitalize())
        dur = c2.number_input("Duración (días)", min_value=0, max_value=730, step=1, value=int(sc0.duration_days or 0),
                              help="0 = sin indicar: se usa una duración típica del tipo de evento (estimada)")
        if st.form_submit_button("Calcular impacto", type="primary"):
            countries, regions, cities = _split_places(places, sc0)
            st.session_state["sc_calc"] = scenario.Scenario(
                title=sc0.title, event_type=event, countries=countries, regions=regions, cities=cities,
                categories=sc0.categories, materials=materials, duration_value=dur or None,
                duration_unit="days" if dur else None).model_dump()


def _result(imp: scenario.ScenarioImpact) -> None:
    """Paso 3: KPIs, mapa y una lista corta de acciones."""
    sc, sup = imp.scenario, load_suppliers()
    dur = (f"{sc.duration_days} días" if sc.duration_days is not None else
           "duración típica del evento (estimada)")
    scope = ", ".join(sc.places) or "todo el mundo"
    md(f'<div style="display:flex;flex-direction:column;gap:6px">'
       f'<h2 class="det-name">{esc(sc.title)}</h2><span class="det-sub">'
       f'{esc(EVENT_LABELS_ES.get(sc.event_type, sc.event_type).capitalize())} · {esc(dur)} · {esc(scope)}'
       '</span></div>')
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
        md('<section class="card"><p class="what">Ningún proveedor queda afectado.</p></section>')
        return

    cds = {c.supplier_id: c for c in imp.countdowns}
    prods = imp.products_table()
    total = sum(s.annual_spend_eur or 0 for s in sup.values())
    with_stock = [c for c in imp.countdowns if c.inventory_days is not None]
    low = min(with_stock, key=lambda c: c.margin_days) if with_stock else None
    deficit = [c for c in imp.countdowns if c.deficit_days > 0]
    kpis([
        kpi("Proveedores", str(len(imp.hits)), unit=f"de {len(sup)}",
            sub=f"{sum(h.supplier.single_source for h in imp.hits)} proveedor(es) único(s) · "
                f"{len(deficit)} con rotura prevista"),
        kpi("Medicamentos", str(len(prods)),
            sub=esc(" · ".join(p["product"].split()[0] for p in prods)) or "ninguno"),
        kpi("Gasto expuesto", meur(imp.spend_exposed), unit="M€",
            sub=f"{pct(imp.spend_exposed / total)} del gasto anual · {meur(imp.spend_at_risk)} M€ con rotura"),
        kpi("Peor margen", signed(low.margin_days) if low else "—", unit="días" if low else "",
            color=T.RED if low and low.margin_days < 0 else "", alert=bool(low and low.margin_days < 0),
            sub=esc(short_supplier(sup[low.supplier_id].name)) if low else "sin proveedores con stock"),
    ])

    left, right = st.columns([7, 5], gap="medium")
    with left:
        exposure = {h.supplier.id: {"margin": cds[h.supplier.id].margin_days, "status": cds[h.supplier.id].status,
                                    "label": map_label(h.supplier.id, cds[h.supplier.id].margin_days,
                                                     no_stock=cds[h.supplier.id].inventory_days is None),
                                    "hover": "; ".join(h.reasons)} for h in imp.hits}
        with st.container(key="panel-simmap"):
            md(head("Dónde golpea", "Tamaño = gasto anual · pulsa un proveedor para ver su ficha"))
            sheet.clickable_chart(risk_map(exposure, fit=True), key="map-sim")
            present = [s for s in STATUS_DOT if any(e["status"] == s for e in exposure.values())]
            md(dot_legend([STATUS_DOT[s] for s in present] + [("Fuera del escenario", T.GREY_DOT)]))
    with right:
        items = []
        for c in sorted(imp.countdowns, key=lambda c: (c.inventory_days is None, c.margin_days))[:4]:
            s = sup[c.supplier_id]
            step = plan_steps(c, s, urgent=c.deficit_days > 0)[0]
            items.append(f'<li><span class="num i">{len(items) + 1}</span><span class="b"><span class="x">'
                         f'{esc(step.text)}</span><span class="o">{esc(short_supplier(s.name))} · '
                         f'{esc(step.owner)} · {esc(step.when)}</span></span></li>')
        md('<section class="card">' + head("Acciones", "Una por proveedor, del menor al mayor margen. El plan "
                                           "completo está en la ficha de cada proveedor")
           + '<ol class="steps">' + "".join(items) + "</ol></section>")


def render() -> None:
    llm_up = cache.llm_up()
    examples = cache.examples()
    loaded = st.session_state.get("sc_loaded")
    md('<h1 class="h1">Simulador «¿Y si…?»</h1>')
    stepper = st.empty()                       # el indicador se pinta al final, cuando ya se sabe el paso

    # Paso 1 · Escenario: texto libre y ejemplos como chips
    with st.container(key="panel-siminput"):
        md(head("¿Qué pasaría si…?", "La IA solo traduce tu pregunta; los proveedores, los márgenes y el plan los "
                "calcula el sistema con los datos de Helixa"))
        st.text_area("Escribe un escenario", key="sc_text", height=100, disabled=not llm_up,
                     placeholder="¿Y si se inunda Gujarat 3 semanas?", label_visibility="collapsed")
        if examples:
            with st.container(key="sc-chips", horizontal=True):
                for i, ex in enumerate(examples):
                    st.button(ex["text"], key=f"sc_ex_{i}", on_click=use_example, args=(examples, i))
        st.button("Interpretar con la IA", on_click=run_interpret, disabled=not llm_up, type="primary",
                  key="sc_interpret")
        if not llm_up:
            md(f'<div class="trust"><span>{T.ICON_WARN}IA local no disponible: usa un ejemplo'
               f'{tip("Los ejemplos ya están interpretados; puedes corregirlos. El cálculo no necesita la IA.")}'
               '</span></div>')
        if not examples:
            md('<span class="sub">Sin ejemplos: python scripts/build_scenarios.py</span>')
        if st.session_state.get("sc_error"):
            st.error(st.session_state["sc_error"])

    # Paso 2 · Revisa: aparece al cargar un escenario
    if loaded:
        with st.container(key="panel-simform"):
            _form(loaded)
    # Paso 3 · Impacto: aparece al calcular
    calc = st.session_state.get("sc_calc")
    with stepper:
        _stepper(3 if calc else 2 if loaded else 1)
    if calc:
        _result(scenario.simulate(scenario.Scenario.model_validate(calc)))
    sheet.open_requested()
