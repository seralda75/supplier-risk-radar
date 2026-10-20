"""Centro de control (docs/mockup_centro_control.html): ¿hay riesgo, dónde, cuánto tiempo tengo y qué hago?

Cabecera · zona de decisión (banner, 5 KPIs, cola «Requiere tu decisión» y detalle de la alerta: qué
pasa, cita, impacto, plan en pasos, fiabilidad y decisión) · calendario de roturas + mapa · treemap
del gasto en riesgo.

Rendimiento: la zona de decisión es un st.fragment. Elegir una tarjeta, «Revisar ahora», «Aprobar plan»
o «Reabrir» solo vuelven a ejecutar esa zona; los gráficos no se tocan. «Falsa alarma» (o reabrir una
falsa alarma) cambia la exposición, y entonces se redibuja la página entera.
"""
from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from core import feedback, results
from core.actions import plan_steps
from core.countdown import Countdown
from core.labels import CRITICALITY_ES, material_es, product_es, product_short, short_supplier
from core.suppliers import load_suppliers

from . import cache, sheet
from . import theme as T
from .components import STATUS_DOT, dot_legend, esc, kpi, kpis, map_label, md, risk_map
from .treemap import STATES, spend_treemap
from .data import EVENT_SHORT, Alert, margin_color, meur, pct, quote_for, signed, status_chip, when

FORM_WORDS = (" inyectable", " comprimidos", " cápsulas")
USER = "director de compras (panel)"
HORIZON = 90          # días que cubre el calendario de roturas
AXIS_START = -6       # un poco de aire a la izquierda para que se vea la línea de «hoy»
LEVEL_RANK = {"critica": 0, "vigilar": 1, "seguimiento": 2}


# ---------------------------------------------------------------------------
# Alertas + decisiones de los compradores
# ---------------------------------------------------------------------------

@dataclass
class Board:
    """Las alertas de un conjunto con las decisiones aplicadas. Una falsa alarma deja de contar en los
    KPIs, el calendario, el mapa y el treemap; un plan aprobado sigue contando (el riesgo no ha pasado),
    pero ya no está pendiente de decisión."""
    alerts: list[Alert]
    verdicts: dict[str, dict]

    def verdict(self, a: Alert) -> str | None:
        v = self.verdicts.get(a.id)
        return v["verdict"] if v else None

    def dismissed(self, a: Alert) -> bool:
        return self.verdict(a) == "falsa_alarma"

    @property
    def active(self) -> list[Alert]:
        return [a for a in self.alerts if not self.dismissed(a)]

    @property
    def critical(self) -> list[Alert]:
        return [a for a in self.active if a.level == "critica"]

    @property
    def pending(self) -> list[Alert]:
        return [a for a in self.critical if self.verdict(a) is None]

    @property
    def queue(self) -> list[Alert]:
        """Críticas y de vigilar: primero las pendientes, luego las decididas (cada grupo por margen)."""
        q = [a for a in self.alerts if a.level in ("critica", "vigilar")]
        return sorted(q, key=lambda a: (self.dismissed(a), self.verdict(a) is not None))

    @property
    def rest(self) -> list[Alert]:
        return [a for a in self.alerts if a.level == "seguimiento"]


def board(split: str) -> Board:
    return Board(cache.alerts(split), cache.decisions(split))


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def _select(split: str, news_id: str) -> None:
    st.session_state[f"sel-{split}"] = news_id


def _decide(split: str, news_id: str, verdict: str, previous: str | None = None) -> None:
    feedback.save(split, news_id, verdict, user=USER, con=cache.db())
    st.session_state["toast"] = {"plan_aprobado": ("Plan aprobado · registrado en la auditoría", "✅"),
                                 "falsa_alarma": ("Marcada como falsa alarma · registrado en la auditoría", "🚫"),
                                 "reabierta": ("Decisión reabierta · vuelve a estar pendiente", "↩️")}[verdict]
    if "falsa_alarma" in (verdict, previous):        # cambia la exposición: también gráficos y mapa
        st.session_state["full_rerun"] = True


def _set_split() -> None:
    st.session_state["split"] = st.session_state["split_widget"]


# ---------------------------------------------------------------------------
# Cabecera, banner y KPIs
# ---------------------------------------------------------------------------

def header(split: str, data: dict) -> None:
    left, stamp, mid, right = st.columns([3.6, 1.5, 1.9, 1.45], vertical_alignment="bottom")
    left.markdown('<div style="display:flex;flex-direction:column;gap:4px"><span class="overline">Riesgo de suministro'
                  '</span><h1 class="h1">Centro de control</h1></div>', unsafe_allow_html=True)
    stamp.markdown(f'<div class="stamp">Datos del {esc(when(data["generated"]))}</div>', unsafe_allow_html=True)
    splits = list(results.SPLITS)
    mid.selectbox("Noticias", splits, index=splits.index(split), key="split_widget", on_change=_set_split,
                  label_visibility="collapsed",
                  format_func=lambda s: {"test": "Noticias de test (entrega)", "validation": "Validación",
                                         "train": "Entrenamiento"}[s])
    with right.container(key="go-sim"):
        st.page_link("views/simulator.py", label="Simular escenario", width="stretch")


def banner(split: str, b: Board) -> None:
    if b.pending:
        top = min(b.pending, key=lambda a: a.margin)
        n = len(b.pending)
        title = f"{n} situaci{'ones críticas requieren' if n > 1 else 'ón crítica requiere'} tu decisión hoy"
        prod = product_es(top.products[0]) if top.products else short_supplier(top.supplier.name)
        if top.worst.inventory_days is None:
            sub = f"{short_supplier(top.supplier.name)} no tiene stock de reserva: impacto inmediato si no se actúa."
        elif top.margin < 0:
            sub = f"Rotura de stock prevista en {prod} dentro de {top.worst.tts_days:.0f} días si no se actúa."
        else:
            sub = f"El menor margen es de {signed(top.margin)} días ({short_supplier(top.supplier.name)})."
        with st.container(key="banner-red"):
            c1, c2 = st.columns([5, 1.1], vertical_alignment="center")
            c1.markdown(f'<div class="banner">{T.ICON_ALERT}<div><span class="t">{esc(title)}</span>'
                        f'<span class="s">{esc(sub)}</span></div></div>', unsafe_allow_html=True)
            c2.button("Revisar ahora", key="review-now", type="primary", on_click=_select, args=(split, top.id),
                      width="stretch", help=f"Abre la más urgente: {top.supplier.name}")
        return
    if b.critical:
        n = len(b.critical)
        title = (f"Las {n} situaciones críticas tienen un plan aprobado" if n > 1 else
                 "La situación crítica tiene un plan aprobado")
        sub = "Siguen en la cola para su seguimiento; cualquier decisión se puede reabrir."
    else:
        n = len(b.active)
        title = "Sin situaciones críticas"
        sub = f"{n} alerta{'s' if n != 1 else ''} en seguimiento: pueden esperar al informe semanal."
    with st.container(key="banner-ok"):
        md(f'<div class="banner">{T.ICON_OK_BIG}<div><span class="t">{esc(title)}</span>'
           f'<span class="s">{esc(sub)}</span></div></div>')


def kpi_row(b: Board) -> None:
    sup = load_suppliers()
    active = b.active
    watch = [a for a in active if a.level == "vigilar"]
    exposed = sorted({c.supplier_id for a in active for c in [a.worst] + a.others})
    unique = sum(sup[i].single_source for i in exposed)
    prods: list[str] = []
    for a in b.critical + watch:
        prods += [p for p in a.products if p not in prods]
    spend = sum(sup[i].annual_spend_eur or 0 for i in exposed)
    total = sum(s.annual_spend_eur or 0 for s in sup.values())
    pool = [a for a in b.critical if a.worst.inventory_days is not None] or \
           [a for a in active if a.worst.inventory_days is not None]
    low = min(pool, key=lambda a: a.margin) if pool else None
    approved = len(b.critical) - len(b.pending)
    dismissed = len(b.alerts) - len(active)
    crit_sub = [f"sin decidir · de {len(active)} activas"]
    if approved:
        crit_sub.append(f"{approved} con plan aprobado")
    if dismissed:
        crit_sub.append(f"{dismissed} descartada{'s' if dismissed > 1 else ''}")
    if not approved and not dismissed:
        crit_sub.append(f"{len(watch)} en vigilancia")
    items = [
        kpi("Alertas críticas", str(len(b.pending)), color=T.RED if b.pending else "", sub=" · ".join(crit_sub)),
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


# ---------------------------------------------------------------------------
# Cola y detalle
# ---------------------------------------------------------------------------

def queue_item(a: Alert, selected: bool, verdict: str | None) -> str:
    text, color = status_chip(a)
    if verdict == "falsa_alarma":
        text, color = "FALSA ALARMA · DESCARTADA", "grey"
    chips = f'<span class="chip {color}">{text}</span>'
    if verdict and verdict != "falsa_alarma":
        chips += f'<span class="chip green">✓ {esc(feedback.VERDICTS[verdict]).upper()}</span>'
    est = '<span class="e"> estimado</span>' if a.estimated and a.worst.inventory_days is not None else ""
    m_txt = f"{signed(a.margin)} d" if a.worst.inventory_days is not None else "sin stock"
    prod = product_es(a.products[0]) if a.products else "sin medicamentos asociados"
    cls = "qitem" + (" sel" if selected else "") + (" off" if verdict == "falsa_alarma" else
                                                    " done" if verdict else "")
    return (f'<div class="{cls}"><span class="top"><span class="chips">{chips}</span>'
            f'<span class="num m" style="color:{margin_color(a.margin, a.level)}">{m_txt}{est}</span></span>'
            f'<span><span class="n">{esc(a.supplier.name)}</span><span class="w">{esc(a.place)} · '
            f'{esc(a.what_short)}</span></span>'
            f'<span class="a">Afecta a <strong>{esc(prod)}</strong> · {esc(a.affects_note)}</span></div>')


def queue(split: str, b: Board, sel: str) -> None:
    with st.container(key="panel-queue"):
        md('<div class="card-head"><h2 class="h2" id="cola-t">Requiere tu decisión</h2>'
           '<span class="sub">Pendientes primero, por días de margen</span></div>')
        if not b.queue:
            md('<p class="sub">Nada pendiente: no hay alertas críticas ni en riesgo latente.</p>')
        for a in b.queue:
            with st.container(key=f"qcard-{a.id}"):
                md(queue_item(a, a.id == sel, b.verdict(a)))
                st.button(f"Ver {a.supplier.name}", key=f"qbtn-{a.id}", on_click=_select, args=(split, a.id))
        if b.rest:
            # Plegado: el director ve primero solo lo que requiere decisión; el resto, a un clic
            exp = st.expander(f"En seguimiento semanal · {len(b.rest)}", expanded=any(a.id == sel for a in b.rest))
            for a in b.rest:
                with exp.container(key=f"qcard-{a.id}"):
                    v = b.verdict(a)
                    tag = ""
                    if v:
                        tag = (f' · <span class="chip {"grey" if v == "falsa_alarma" else "green"}">'
                               f'{esc(feedback.VERDICTS[v])}</span>')
                    elif a.r.get("needs_review"):
                        tag = ' · <span class="chip amber">revisar</span>'
                    m_txt = f"{signed(a.margin)} d" if a.worst.inventory_days is not None else "sin corte"
                    sel_style = f' style="border:2px solid {T.PURPLE};background:{T.PURPLE_SOFT}"' if a.id == sel else ""
                    off = ";text-decoration:line-through;opacity:.6" if v == "falsa_alarma" else ""
                    md(f'<div class="qrow"{sel_style}><span><strong>{esc(a.supplier.name)}</strong>{tag}'
                       f'<span class="w" style="display:block">{esc(a.place)} · {esc(a.what_short)}</span></span>'
                       f'<span class="num" style="color:{margin_color(a.margin, a.level)};font-weight:600{off}">'
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


def _news(a: Alert) -> str:
    """La noticia completa (el reto no trae enlaces: titular, resumen, fuente y fecha)."""
    r = a.r
    return (f'<div class="news-body"><span class="sub">{esc(r.get("source") or "Fuente desconocida")} · '
            f'{esc((r.get("published_date") or "")[:10])} · {esc(a.id)} · '
            f'{esc(EVENT_SHORT.get(r["event_type"], r["event_type"]))}</span>'
            f'<span class="hl">{esc(r["headline"])}</span><span>{esc(r.get("summary") or "")}</span></div>')


def _decided(verdict: dict) -> str:
    v = verdict["verdict"]
    who = f'· {esc(verdict["user"])} · {esc(when(verdict["ts"]))} · registrado en la auditoría'
    if v == "falsa_alarma":
        return (f'<div class="decided fa">{T.ICON_WARN}Falsa alarma <span class="w">{who}. No cuenta en los '
                'indicadores, el calendario ni el mapa.</span></div>')
    return f'<div class="decided ok">{T.ICON_CHECK}{esc(feedback.VERDICTS[v])} <span class="w">{who}</span></div>'


def detail(split: str, a: Alert, verdict: dict | None) -> None:
    s = a.supplier
    text, color = status_chip(a)
    with st.container(key="panel-detail"):
        head, link = st.columns([3.4, 1.6], vertical_alignment="top")
        head.markdown(f'<div style="display:flex;flex-direction:column;gap:6px"><span class="chip {color}">{text}</span>'
                      f'<h2 class="det-name" id="det-t">{esc(s.name)}</h2><span class="det-sub">{esc(a.place)} · '
                      f'{esc(material_es(s.material))}</span></div>', unsafe_allow_html=True)
        with link.popover("Ver noticia original", type="tertiary", key=f"news-{split}-{a.id}"):
            md(_news(a))
        quote, _ = quote_for(a.r)
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
            if not verdict:
                c1, c2, c3 = st.columns([2.6, 1.15, 1.2], vertical_alignment="center")
                c1.markdown(_trust(a), unsafe_allow_html=True)
                c2.button("Falsa alarma", key=f"fa-{split}-{a.id}", on_click=_decide,
                          args=(split, a.id, "falsa_alarma"), width="stretch")
                c3.button("Aprobar plan", key=f"ok-{split}-{a.id}", type="primary", on_click=_decide,
                          args=(split, a.id, "plan_aprobado"), width="stretch")
            else:
                c1, c2 = st.columns([3.8, 1.15], vertical_alignment="center")
                c1.markdown(_trust(a) + _decided(verdict), unsafe_allow_html=True)
                c2.button("Reabrir", key=f"re-{split}-{a.id}", on_click=_decide,
                          args=(split, a.id, "reabierta", verdict["verdict"]), width="stretch",
                          help="Vuelve a dejar la alerta pendiente (la auditoría conserva las dos decisiones)")


@st.fragment
def decision_zone(split: str) -> None:
    """Banner + KPIs + cola + detalle: un clic aquí solo vuelve a ejecutar esta función."""
    if st.session_state.pop("full_rerun", False):
        st.rerun(scope="app")
    if toast := st.session_state.pop("toast", None):
        st.toast(toast[0], icon=toast[1])
    b = board(split)
    sel_key = f"sel-{split}"
    ids = [a.id for a in b.alerts]
    if st.session_state.get(sel_key) not in ids:
        st.session_state[sel_key] = (b.queue or b.alerts)[0].id if ids else None
    sel = st.session_state[sel_key]
    banner(split, b)
    kpi_row(b)
    if not b.alerts:
        md('<section class="card"><p class="what">No hay ninguna noticia de riesgo en este conjunto.</p></section>')
        return
    left, right = st.columns([5, 7], gap="medium")
    with left:
        queue(split, b, sel)
    with right:
        a = next(x for x in b.alerts if x.id == sel)
        detail(split, a, b.verdicts.get(sel))


# ---------------------------------------------------------------------------
# Calendario de roturas
# ---------------------------------------------------------------------------

def _x(day: float) -> float:
    """Posición (%) de un día en el eje del calendario."""
    return 100 * (min(max(day, AXIS_START), HORIZON) - AXIS_START) / (HORIZON - AXIS_START)


def _seg(cls: str, start: float, end: float) -> str:
    if end <= start:
        return ""
    return f'<span class="seg {cls}" style="left:{_x(start):.2f}%;width:{_x(end) - _x(start):.2f}%"></span>'


def calendar_rows(alerts: list[Alert]) -> list[tuple[str, Countdown, Alert]]:
    """Una fila por medicamento: la cuenta atrás del proveedor que antes lo deja sin suministro."""
    best: dict[str, tuple[Countdown, Alert]] = {}
    for a in alerts:
        for c in [a.worst] + a.others:
            if c.inventory_days is None:            # logística y servicios: sin stock ni medicamentos propios
                continue
            for p in c.products:
                if p not in best or c.margin_days < best[p][0].margin_days:
                    best[p] = (c, a)
    return sorted(((p, c, a) for p, (c, a) in best.items()), key=lambda x: (x[1].margin_days, x[0]))


def calendar(alerts: list[Alert]) -> str:
    rows = calendar_rows(alerts)
    head = ('<div class="card-head"><h2 class="h2" id="cal-t">Calendario de roturas</h2>'
            f'<span class="sub">¿Cuánto aguantamos? Próximos {HORIZON} días por medicamento</span></div>')
    if not rows:
        return f'<section class="card">{head}<p class="sub">Ningún medicamento en riesgo en la cola.</p></section>'
    sup = load_suppliers()
    cells = []
    for i, (prod, c, a) in enumerate(rows, 1):
        tts, ttr, est = c.tts_days, c.ttr_days, c.ttr_estimated
        e = " est" if est else ""
        s = sup[c.supplier_id]
        if ttr > tts:                                   # rotura: verde hasta agotar, rojo hasta recuperarse
            bars = _seg("ok", 0, tts) + _seg("out" + e, tts, ttr) + _seg("back" + e, ttr, HORIZON)
        else:                                           # cubierto: el proveedor vuelve antes de agotar el stock
            bars = _seg("ok", 0, ttr) + _seg("back" + e, ttr, HORIZON)
        marks = ""
        if ttr <= HORIZON:
            marks += (f'<span class="mk rec{e}" style="left:{_x(ttr):.2f}%" title="El proveedor se recupera el día '
                      f'{ttr}{" (estimado)" if est else ""}"></span>')
        else:
            marks += f'<span class="more">→ día {ttr}</span>'
        if c.alternate_id and not c.alternate_affected and c.alternate_lead_days is not None \
                and c.alternate_lead_days <= HORIZON:
            alt = short_supplier(sup[c.alternate_id].name)
            marks += (f'<span class="mk alt" style="left:{_x(c.alternate_lead_days):.2f}%" title="Llega el primer '
                      f'envío del alternativo ({esc(alt)}) el día {c.alternate_lead_days:.0f}"></span>')
        title = (f"Stock hasta el día {tts:.0f}; el proveedor se recupera el día {ttr}"
                 f"{' (estimado: la noticia no indica plazo)' if est else ' (según la noticia)'}")
        if c.margin_days < 0:
            state, when_ = ("RIESGO LATENTE" if a.level == "vigilar" else "ROTURA"), f"sin stock día {tts:.0f}"
            state_color = T.AMBER_INK if a.level == "vigilar" else T.RED_INK
        else:
            state, when_, state_color = "CUBIERTO", f"vuelve día {ttr}", T.GREEN
        name = product_es(prod)
        form = next((f.strip() for f in FORM_WORDS if name.endswith(f)), "")
        big = name[: -len(form) - 1] if form else name
        cells.append(
            f'<span class="lbl" style="grid-row:{i};grid-column:1"><strong title="{esc(name)}">{esc(big)}</strong>'
            f'<span class="w" title="{esc(s.name)} · {esc(material_es(s.material))}">'
            f'{esc(form + " · " if form else "")}{esc(short_supplier(s.name))}</span></span>'
            f'<span class="track" style="grid-row:{i};grid-column:2" title="{esc(title)}">{bars}{marks}</span>'
            f'<span class="val" style="grid-row:{i};grid-column:3"><span class="num" style="color:'
            f'{margin_color(c.margin_days, a.level)}">{signed(c.margin_days)} d</span>'
            f'<span class="st" style="color:{state_color}">{state}</span>'
            f'<span class="sub">{when_}{" (estimado)" if est else ""}</span></span>')
    n = len(rows)
    ticks = "".join(f'<span style="left:{_x(d):.2f}%">{d if d < HORIZON else f"{d} días"}</span>'
                    for d in range(15, HORIZON + 1, 15))
    cells.append(f'<span class="axis" style="grid-row:{n + 1};grid-column:2">{ticks}</span>')
    cells.append(f'<span class="today" style="grid-row:1 / span {n + 1};grid-column:2;--x:{_x(0):.2f}%">'
                 f'<span>Hoy</span></span>')
    legend = ('<span class="legend">'
              f'<span><span class="sw" style="background:{T.GREEN}"></span>Con stock</span>'
              f'<span><span class="sw" style="background:{T.RED}"></span>Rotura (sin stock)</span>'
              '<span><span class="sw" style="background:#BFE3CC"></span>Suministro recuperado</span>'
              '<span><span class="mk-rec"></span>Se recupera el proveedor</span>'
              '<span><span class="mk-alt"></span>Llega el alternativo</span>'
              '<span><span class="sw hatch"></span>Plazo estimado</span></span>')
    return (f'<section class="card" style="height:100%">{head}{legend}<div class="cal" role="img" aria-label='
            f'"Calendario de roturas de {n} medicamentos">{"".join(cells)}</div></section>')


# ---------------------------------------------------------------------------
# Mapa y treemap (pulsar un proveedor abre su ficha)
# ---------------------------------------------------------------------------

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
           '<span class="sub">Tamaño = gasto anual · pulsa un proveedor</span></div>')
        sheet.clickable_chart(risk_map(exposure), key="map-control")
        present = [s for s in STATUS_DOT if any(e["status"] == s for e in exposure.values())]
        md(dot_legend([STATUS_DOT[s] for s in present] + [("Sin exposición", T.GREY_DOT)]))


def spend(alerts: list[Alert]) -> None:
    states: dict[str, str] = {}
    for a in alerts:
        for c in [a.worst] + a.others:
            if c.supplier_id not in states or LEVEL_RANK[a.level] < LEVEL_RANK[states[c.supplier_id]]:
                states[c.supplier_id] = a.level
    sup = load_suppliers()
    total = sum(s.annual_spend_eur or 0 for s in sup.values())
    risky = sum(sup[i].annual_spend_eur or 0 for i in states)
    with st.container(key="panel-treemap"):
        md('<div class="card-head"><h2 class="h2" id="tm-t">¿Dónde está el gasto en riesgo?</h2>'
           f'<span class="sub">{meur(risky)} M€ de {meur(total)} M€ de gasto anual en proveedores con alertas · '
           'pulsa un proveedor para ver su ficha</span></div>')
        picked = spend_treemap(states, key="tm-control")
        if picked:
            sheet.request(picked)
        md('<span class="legend">' + "".join(f'<span><span class="sw" style="background:{c};border:1px solid '
                                             f'{T.LINE_2}"></span>{esc(t)}</span>'
                                             for t, c, _ in STATES.values()) + "</span>")
        # El estado, también por escrito (las casillas pequeñas no tienen sitio para el texto)
        lines = []
        for level in ("critica", "vigilar", "seguimiento"):
            ids = sorted((i for i, lv in states.items() if lv == level), key=lambda i: -(sup[i].annual_spend_eur or 0))
            if ids:
                lines.append(f"<strong>{STATES[level][0]}:</strong> " + ", ".join(
                    f"{esc(short_supplier(sup[i].name))} ({meur(sup[i].annual_spend_eur or 0)} M€)" for i in ids))
        if lines:
            md('<p class="sub" style="margin:0">' + " · ".join(lines) + "</p>")


def charts(split: str) -> None:
    b = board(split)
    active = b.active
    in_queue = [a for a in active if a.level in ("critica", "vigilar")]
    left, right = st.columns([7, 5], gap="medium")
    with left:
        md(calendar(in_queue))
    with right:
        where(active, {a.id for a in in_queue})
    spend(active)


def page() -> None:
    split = st.session_state.setdefault("split", "test")
    data = cache.data(split)
    if not data:
        st.warning(f"No hay resultados guardados para «{results.SPLITS[split]}». "
                   f"Genéralos con `python scripts/build_results.py --split {split}`.")
        return
    header(split, data)
    decision_zone(split)
    if cache.alerts(split):
        charts(split)
    md('<footer class="foot">Datos del reto (Helixa Pharmaceuticals, empresa ficticia). Toda decisión requiere '
       'aprobación humana y queda registrada.</footer>')
    sheet.open_requested()
