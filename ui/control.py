"""Centro de control (docs/mockup_centro_control.html): ¿hay riesgo, dónde, cuánto tiempo tengo y qué hago?

Banner de estado · 5 KPIs · cola «Requiere tu decisión» + detalle de la alerta seleccionada (qué pasa,
cita, impacto, plan en pasos, fiabilidad y decisión) · «¿Cuánto aguantamos?» · mapa.
"""
from __future__ import annotations

import streamlit as st

from core import feedback, results
from core.actions import plan_steps
from core.labels import CRITICALITY_ES, material_es, product_es, product_short, short_supplier
from core.suppliers import load_suppliers

from . import theme as T
from .components import (STATUS_DOT, dot_legend, esc, kpi, kpis, map_label, md, risk_map, show_map)
from .data import (Alert, build_alerts, margin_color, meur, nice_ceil, pct, quote_for, signed, status_chip, when)

FORM_WORDS = (" inyectable", " comprimidos", " cápsulas")


def _select(split: str, news_id: str) -> None:
    st.session_state[f"sel-{split}"] = news_id


def _decide(split: str, news_id: str, verdict: str) -> None:
    feedback.save(split, news_id, verdict, user="director de compras (panel)")
    st.toast(f"{feedback.VERDICTS[verdict]} · registrado en la auditoría", icon="✅")


def _set_split() -> None:
    st.session_state["split"] = st.session_state["split_widget"]


def header(split: str, data: dict, go_to) -> None:
    left, stamp, mid, right = st.columns([3.6, 1.5, 1.9, 1.45], vertical_alignment="bottom")
    left.markdown('<div style="display:flex;flex-direction:column;gap:4px"><span class="overline">Riesgo de suministro'
                  '</span><h1 class="h1">Centro de control</h1></div>', unsafe_allow_html=True)
    stamp.markdown(f'<div class="stamp">Datos del {esc(when(data["generated"]))}</div>', unsafe_allow_html=True)
    splits = list(results.SPLITS)
    mid.selectbox("Noticias", splits, index=splits.index(split), key="split_widget", on_change=_set_split,
                  label_visibility="collapsed",
                  format_func=lambda s: {"test": "Noticias de test (entrega)", "validation": "Validación",
                                         "train": "Entrenamiento"}[s])
    right.button("Simular escenario", key="go-sim", on_click=go_to, args=("simulator",), width="stretch")


def banner(split: str, alerts: list[Alert], n_risks: int) -> None:
    crit = [a for a in alerts if a.level == "critica"]
    if crit:
        top = min(crit, key=lambda a: a.margin)
        n = len(crit)
        title = f"{n} situaci{'ones críticas requieren' if n > 1 else 'ón crítica requiere'} tu decisión hoy"
        prod = product_es(top.products[0]) if top.products else short_supplier(top.supplier.name)
        if top.worst.inventory_days is None:
            sub = f"{short_supplier(top.supplier.name)} no tiene stock de reserva: impacto inmediato si no se actúa."
        elif top.margin < 0:
            sub = (f"Rotura de stock prevista en {prod} dentro de {top.worst.tts_days:.0f} días si no se actúa.")
        else:
            sub = f"El menor margen es de {signed(top.margin)} días ({short_supplier(top.supplier.name)})."
        with st.container(key="banner-red"):
            c1, c2 = st.columns([5, 1.1], vertical_alignment="center")
            c1.markdown(f'<div class="banner">{T.ICON_ALERT}<div><span class="t">{esc(title)}</span>'
                        f'<span class="s">{esc(sub)}</span></div></div>', unsafe_allow_html=True)
            c2.button("Revisar ahora", key="review-now", type="primary", on_click=_select, args=(split, top.id),
                      width="stretch")
    else:
        with st.container(key="banner-ok"):
            md(f'<div class="banner">{T.ICON_OK_BIG}<div><span class="t">Sin situaciones críticas</span>'
               f'<span class="s">{n_risks} alerta{"s" if n_risks != 1 else ""} en seguimiento: pueden esperar al '
               'informe semanal.</span></div></div>')


def kpi_row(alerts: list[Alert]) -> None:
    sup = load_suppliers()
    crit = [a for a in alerts if a.level == "critica"]
    watch = [a for a in alerts if a.level == "vigilar"]
    queue = crit + watch
    exposed = sorted({c.supplier_id for a in alerts for c in [a.worst] + a.others})
    unique = sum(sup[i].single_source for i in exposed)
    prods: list[str] = []
    for a in queue:
        prods += [p for p in a.products if p not in prods]
    spend = sum(sup[i].annual_spend_eur or 0 for i in exposed)
    total = sum(s.annual_spend_eur or 0 for s in sup.values())
    pool = [a for a in crit if a.worst.inventory_days is not None] or \
           [a for a in alerts if a.worst.inventory_days is not None]
    low = min(pool, key=lambda a: a.margin) if pool else None
    items = [
        kpi("Alertas críticas", str(len(crit)), color=T.RED if crit else "",
            sub=f"de {len(alerts)} alertas activas · {len(watch)} en vigilancia"),
        kpi("Proveedores expuestos", str(len(exposed)), unit=f"de {len(sup)}",
            sub=f"{unique} {'es proveedor único' if unique == 1 else 'son proveedor único'}"),
        kpi("Medicamentos en riesgo", str(len(prods)),
            sub=esc(" · ".join(product_short(p) for p in prods)) or "ninguno en la cola"),
        kpi("Gasto anual expuesto", meur(spend), unit="M€",
            sub=f"{pct(spend / total)} del gasto total ({meur(total)} M€)"),
    ]
    if low:
        items.append(kpi("Menor margen", signed(low.margin), unit="días", color=margin_color(low.margin, low.level),
                         alert=low.margin < 0,
                         sub=esc(f"{short_supplier(low.supplier.name)} · {material_es(low.supplier.material)}")))
    else:
        items.append(kpi("Menor margen", "—", sub="sin proveedores con stock afectados"))
    kpis(items)


def queue_item(a: Alert, selected: bool, verdict: dict | None) -> str:
    text, color = status_chip(a)
    est = '<span class="e"> estimado</span>' if a.estimated and a.worst.inventory_days is not None else ""
    m_txt = f"{signed(a.margin)} d" if a.worst.inventory_days is not None else "sin stock"
    prod = product_es(a.products[0]) if a.products else "sin medicamentos asociados"
    decided = ""
    if verdict:
        decided = f' · <span class="chip {"green" if verdict["verdict"] != "falsa_alarma" else "grey"}">' \
                  f'{esc(feedback.VERDICTS[verdict["verdict"]])}</span>'
    return (f'<div class="qitem{" sel" if selected else ""}"><span class="top"><span class="chip {color}">{text}</span>'
            f'<span class="num m" style="color:{margin_color(a.margin, a.level)}">{m_txt}{est}</span></span>'
            f'<span><span class="n">{esc(a.supplier.name)}</span><span class="w">{esc(a.place)} · '
            f'{esc(a.what_short)}</span></span>'
            f'<span class="a">Afecta a <strong>{esc(prod)}</strong> · {esc(a.affects_note)}{decided}</span></div>')


def queue(split: str, queue_alerts: list[Alert], rest: list[Alert], sel: str, verdicts: dict) -> None:
    with st.container(key="panel-queue"):
        md('<div class="card-head"><h2 class="h2" id="cola-t">Requiere tu decisión</h2>'
           '<span class="sub">Ordenado por días de margen</span></div>')
        if not queue_alerts:
            md('<p class="sub">Nada pendiente: no hay alertas críticas ni en riesgo latente.</p>')
        for a in queue_alerts:
            with st.container(key=f"qcard-{a.id}"):
                md(queue_item(a, a.id == sel, verdicts.get(a.id)))
                st.button(f"Ver {a.supplier.name}", key=f"qbtn-{a.id}", on_click=_select, args=(split, a.id))
        if rest:
            # Plegado: el director ve primero solo lo que requiere decisión; el resto, a un clic
            exp = st.expander(f"En seguimiento semanal · {len(rest)}", expanded=any(a.id == sel for a in rest))
            for a in rest:
                with exp.container(key=f"qcard-{a.id}"):
                    review = ' · <span class="chip amber">revisar</span>' if a.r.get("needs_review") else ""
                    m_txt = f"{signed(a.margin)} d" if a.worst.inventory_days is not None else "sin corte"
                    sel_style = f' style="border:2px solid {T.PURPLE};background:{T.PURPLE_SOFT}"' if a.id == sel else ""
                    md(f'<div class="qrow"{sel_style}><span><strong>{esc(a.supplier.name)}</strong>{review}'
                       f'<span class="w" style="display:block">{esc(a.place)} · {esc(a.what_short)}</span></span>'
                       f'<span class="num" style="color:{margin_color(a.margin, a.level)};font-weight:600">'
                       f'{m_txt}</span></div>')
                    st.button(f"Ver {a.supplier.name}", key=f"qbtn-{a.id}", on_click=_select, args=(split, a.id))


def _impact_boxes(a: Alert) -> str:
    c, s = a.worst, a.supplier
    if c.inventory_days is None:
        margin_box = (f'<div class="box red"><span class="l">Margen</span><span class="num v">Inmediato</span>'
                      f'<span class="s">sin stock de reserva · {c.ttr_days} d hasta recuperarse'
                      f'{" (estimado)" if c.ttr_estimated else ""}</span></div>')
    else:
        cls = "red" if c.margin_days < 0 else ("amber" if c.status in ("margen_ajustado", "riesgo_latente") else "green")
        stock = f"{c.inventory_days:.0f} d de stock"
        if c.alternate_margin_days:
            stock += f" + {c.alternate_margin_days:.0f} d del alternativo"
        margin_box = (f'<div class="box {cls}"><span class="l">Margen</span>'
                      f'<span class="num v">{signed(c.margin_days)} días</span>'
                      f'<span class="s">{stock} frente a {c.ttr_days} d de '
                      f'{"recuperación estimada" if c.ttr_estimated else "retraso"}</span></div>')
    prods = a.products
    if prods:
        name = product_es(prods[0])
        form = next((f.strip() for f in FORM_WORDS if name.endswith(f)), "")
        big = name[: -len(form) - 1] if form else name
        sub = form + (f" · y {len(prods) - 1} más" if len(prods) > 1 else "")
        med_box = (f'<div class="box"><span class="l">Medicamento{"s" if len(prods) > 1 else ""} afectado'
                   f'{"s" if len(prods) > 1 else ""}</span><span class="t">{esc(big)}</span>'
                   f'<span class="s">{esc(sub)}</span></div>')
    else:
        med_box = ('<div class="box"><span class="l">Medicamento afectado</span><span class="t">—</span>'
                   '<span class="s">servicio sin medicamentos asociados</span></div>')
    dep = "proveedor único" if s.single_source else "con alternativo aprobado"
    spend_box = (f'<div class="box"><span class="l">Gasto anual</span><span class="num v">{meur(s.annual_spend_eur or 0)} M€'
                 f'</span><span class="s">{dep} · criticidad {CRITICALITY_ES.get(s.criticality, s.criticality)}</span></div>')
    return f'<div class="boxes">{margin_box}{med_box}{spend_box}</div>'


def _trust(a: Alert) -> str:
    r = a.r
    lines = []
    if r.get("consensus") is True:
        lines.append((T.ICON_CHECK, "Reglas e IA coinciden en el diagnóstico"))
    elif r.get("consensus") is False:
        lines.append((T.ICON_WARN, "Reglas e IA no coinciden: requiere revisión humana"))
    else:
        lines.append((T.ICON_WARN, "Diagnóstico solo con reglas (IA no disponible)"))
    if r.get("recovery_reported") and not a.estimated:
        lines.append((T.ICON_CHECK, f"Duración «{r['recovery_reported']}» citada en la noticia"))
    elif a.worst.ttr_days:
        lines.append((T.ICON_WARN, f"Plazo estimado ({a.worst.ttr_days} d): la noticia no indica duración"))
    if "confianza_baja" in (r.get("review_reasons") or []):
        lines.append((T.ICON_WARN, "La IA declara poca confianza"))
    return '<div class="trust">' + "".join(f"<span>{i}{esc(t)}</span>" for i, t in lines) + "</div>"


def detail(split: str, a: Alert, verdict: dict | None) -> None:
    s, r = a.supplier, a.r
    text, color = status_chip(a)
    with st.container(key="panel-detail"):
        news = (f'<details class="news"><summary>Ver noticia original</summary><div class="body"><strong>'
                f'{esc(r["headline"])}</strong><br>{esc(r.get("summary") or "")}<br><span class="sub">'
                f'{esc(r.get("source") or "")} · {esc((r.get("published_date") or "")[:10])} · {esc(a.id)}'
                f'</span></div></details>')
        md(f'<div class="card-head" style="align-items:flex-start"><div style="display:flex;flex-direction:column;'
           f'gap:6px"><span class="chip {color}">{text}</span><h2 class="det-name" id="det-t">{esc(s.name)}</h2>'
           f'<span class="det-sub">{esc(a.place)} · {esc(material_es(s.material))}</span></div>{news}</div>')
        quote, _ = quote_for(r)
        md(f'<div style="display:flex;flex-direction:column;gap:8px"><h3 class="h3">Qué pasa</h3>'
           f'<p class="what">{esc(a.what())}</p><blockquote class="quote">«{quote}»</blockquote></div>')
        md(_impact_boxes(a))
        steps = plan_steps(a.worst, s, urgent=a.level == "critica")
        md('<div style="display:flex;flex-direction:column;gap:10px"><h3 class="h3">Plan recomendado</h3>'
           '<ol class="steps">' + "".join(
               f'<li><span class="num i">{i}</span><span class="b"><span class="x">{esc(st_.text)}</span>'
               f'<span class="o">{esc(st_.owner)} · {esc(st_.when)}</span></span></li>'
               for i, st_ in enumerate(steps, 1)) + "</ol></div>")
        with st.container(key="decision"):
            c1, c2, c3 = st.columns([2.6, 1.15, 1.2], vertical_alignment="center")
            extra = ""
            if verdict:
                extra = (f'<span>{T.ICON_CHECK if verdict["verdict"] != "falsa_alarma" else T.ICON_WARN}'
                         f'{esc(feedback.VERDICTS[verdict["verdict"]])} · {esc(verdict["user"])} · '
                         f'{esc(when(verdict["ts"]))}</span>')
            c1.markdown(_trust(a).replace("</div>", extra + "</div>"), unsafe_allow_html=True)
            c2.button("Falsa alarma", key=f"fa-{split}-{a.id}", on_click=_decide, args=(split, a.id, "falsa_alarma"),
                      width="stretch")
            c3.button("Aprobar plan", key=f"ok-{split}-{a.id}", type="primary", on_click=_decide,
                      args=(split, a.id, "plan_aprobado"), width="stretch")


def hold_chart(queue_alerts: list[Alert]) -> str:
    rows = [a for a in queue_alerts if a.worst.inventory_days is not None] or queue_alerts
    if not rows:
        return '<p class="sub">No hay alertas en la cola.</p>'
    scale = nice_ceil(max(max(a.worst.tts_days, a.worst.ttr_days) for a in rows))
    ticks = [round(scale * i / 4) for i in range(5)]
    out = []
    for a in rows:
        c = a.worst
        col = margin_color(a.margin, a.level)
        dash = T.RED if (a.margin < 0 and a.level == "critica") else T.AMBER
        opac = ";opacity:.7" if a.level == "vigilar" else ""
        star = "*" if a.estimated else ""
        out.append(f'<div class="row"><span class="lbl" title="{esc(a.supplier.name)}">'
                   f'{esc(short_supplier(a.supplier.name))}</span><span class="bars">'
                   f'<span class="stock" style="width:{100 * c.tts_days / scale:.1f}%"></span>'
                   f'<span class="rec" style="width:{100 * c.ttr_days / scale:.1f}%;border-color:{dash}{opac}"></span>'
                   f'</span><span class="num v" style="color:{col}">{signed(a.margin)} d{star}</span></div>')
    out.append('<div class="row"><span></span><span class="num axis">' +
               "".join(f"<span>{t}{' días' if i == 4 else ''}</span>" for i, t in enumerate(ticks)) +
               "</span><span></span></div>")
    note = ('<span class="sub">* Tiempo de recuperación estimado: la noticia no indica plazo.</span>'
            if any(a.estimated for a in rows) else "")
    legend = (f'<span class="legend"><span><span class="sw" style="background:{T.INK_2}"></span>Stock disponible</span>'
              f'<span><span class="sw" style="border:2px dashed {T.RED};box-sizing:border-box"></span>'
              'Tiempo de recuperación</span></span>')
    return (f'<section class="card" style="gap:18px;height:100%"><div class="card-head"><h2 class="h2" id="ag-t">'
            f'¿Cuánto aguantamos?</h2>{legend}</div><div class="hold">{"".join(out)}</div>{note}</section>')


def where(alerts: list[Alert], queue_ids: set[str]) -> None:
    exposure: dict[str, dict] = {}
    for a in alerts:
        for c in [a.worst] + a.others:
            prev = exposure.get(c.supplier_id)
            if prev is None or c.margin_days < prev["margin"]:
                lab = map_label(c.supplier_id, c.margin_days, c.ttr_estimated, c.inventory_days is None) if (
                    a.id in queue_ids and c is a.worst) else ""
                exposure[c.supplier_id] = {
                    "margin": c.margin_days, "status": c.status, "label": lab,
                    "hover": f"{STATUS_DOT[c.status][0]} · margen {signed(c.margin_days)} d"
                             + (" (estimado)" if c.ttr_estimated else "")}
    with st.container(key="panel-map"):
        md('<div class="card-head"><h2 class="h2" id="map-t">Dónde está el riesgo</h2>'
           '<span class="sub">Tamaño = gasto anual</span></div>')
        show_map(risk_map(exposure), key="map-control")
        present = [s for s in STATUS_DOT if any(e["status"] == s for e in exposure.values())]
        md(dot_legend([STATUS_DOT[s] for s in present] + [("Sin exposición", T.GREY_DOT)]))


def render(split: str, data: dict, go_to) -> None:
    res = data["results"]
    alerts = build_alerts(res)
    verdicts = feedback.latest(split)
    queue_alerts = [a for a in alerts if a.level in ("critica", "vigilar")]
    rest = [a for a in alerts if a.level == "seguimiento"]
    sel_key = f"sel-{split}"
    ids = [a.id for a in alerts]
    if st.session_state.get(sel_key) not in ids:
        st.session_state[sel_key] = ids[0] if ids else None
    sel = st.session_state[sel_key]

    header(split, data, go_to)
    banner(split, alerts, len(alerts))
    kpi_row(alerts)
    if not alerts:
        md('<section class="card"><p class="what">No hay ninguna noticia de riesgo en este conjunto.</p></section>')
    else:
        left, right = st.columns([5, 7], gap="medium")
        with left:
            queue(split, queue_alerts, rest, sel, verdicts)
        with right:
            detail(split, next(a for a in alerts if a.id == sel), verdicts.get(sel))
        left, right = st.columns([7, 5], gap="medium")
        with left:
            md(hold_chart(queue_alerts))
        with right:
            where(alerts, {a.id for a in queue_alerts})
    md('<footer class="foot">Datos del reto (Helixa Pharmaceuticals, empresa ficticia). Toda decisión requiere '
       'aprobación humana y queda registrada.</footer>')
