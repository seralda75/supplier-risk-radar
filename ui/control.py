"""Centro de control (docs/mockup_centro_control.html): ¿hay riesgo, dónde, cuánto tiempo tengo y qué hago?

Cabecera · zona de decisión (banner, 5 KPIs; a la izquierda la cola «Requiere tu decisión» y las acciones
en curso; a la derecha el detalle de la alerta y el mapa) · calendario de roturas · treemap del gasto en
riesgo. Pulsar una tarjeta abre la alerta en una ventana (información + decisión): aprobar el plan,
falsa alarma con motivo, crear un pedido o un recordatorio. Todo se guarda en SQLite.

Rendimiento: la zona de decisión es un st.fragment: elegir una tarjeta o marcar una acción como hecha
solo vuelve a ejecutar esa zona. Una decisión (aprobar, falsa alarma, reabrir) cambia KPIs, calendario,
mapa y treemap: se guarda y se vuelve a ejecutar la página entera (st.rerun), sin estado intermedio.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import streamlit as st

from core import feedback, results, tasks
from core.actions import plan_steps
from core.countdown import Countdown
from core.labels import CRITICALITY_ES, material_es, product_es, product_short, short_supplier
from core.suppliers import load_suppliers

from . import cache, comms_view, demo_view, sheet
from . import theme as T
from .components import STATUS_DOT, dot_legend, esc, kpi, kpis, map_label, md, risk_map
from .treemap import GROUP, REST, STATES, groups as tm_groups, spend_treemap
from .data import EVENT_SHORT, Alert, margin_color, meur, pct, quote_for, signed, status_chip, when

FORM_WORDS = (" inyectable", " comprimidos", " cápsulas")
USER = "director de compras (panel)"
HORIZON = 90          # días que cubre el calendario de roturas
AXIS_START = -6       # un poco de aire a la izquierda para que se vea la línea de «hoy»
LEVEL_RANK = {"critica": 0, "vigilar": 1, "seguimiento": 2}
MONTHS = "ene feb mar abr may jun jul ago sep oct nov dic".split()
WHEN_DAYS = {"hoy": 1, "48 h": 2, "1 semana": 7, "semanal": 7, "si se alarga": 7}   # plazo del plan -> recordatorio


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
        """Críticas y de vigilar, por nivel y días de margen. El orden no cambia al decidir: la tarjeta
        decidida se queda en su sitio y cambia de aspecto, para que se vea qué ha pasado."""
        return [a for a in self.alerts if a.level in ("critica", "vigilar")]

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


def _open(split: str, news_id: str) -> None:
    """Callback de una tarjeta: la elige y abre su ventana. La ventana sigue abierta (aunque la página se
    vuelva a ejecutar) hasta que el usuario la cierra (_close) o toma una decisión (decide)."""
    _select(split, news_id)
    st.session_state["alert_dialog"] = (split, news_id)


def _close() -> None:
    """Al cerrar la ventana con la X o pulsando fuera de ella."""
    st.session_state.pop("alert_dialog", None)


def decide(split: str, a: Alert, verdict: str, note: str = "") -> None:
    """Guarda la decisión y vuelve a ejecutar la página entera: KPIs, tarjeta, calendario, mapa y treemap
    salen ya con la decisión aplicada, y el aviso se muestra al principio de la ejecución siguiente."""
    feedback.save(split, a.id, verdict, user=USER, note=note.strip(), con=cache.db())
    st.session_state.pop("alert_dialog", None)          # la decisión cierra la ventana
    name = short_supplier(a.supplier.name)
    st.session_state["toast"] = {
        "plan_aprobado": (f"Plan aprobado · {name} · registrado en la auditoría", "✅"),
        "falsa_alarma": (f"Falsa alarma · {name} sale de los indicadores, el calendario y el mapa", "🚫"),
        "reabierta": (f"Decisión reabierta · {name} vuelve a estar pendiente", "↩️")}[verdict]
    st.rerun()


def _done(kind: str, item_id: int) -> None:
    tasks.mark_done(kind, item_id, con=cache.db())
    st.session_state["toast"] = ("Acción marcada como hecha", "✔️")


def day_es(iso: str) -> str:
    """'2026-10-22' -> '22 oct'."""
    try:
        d = date.fromisoformat(iso[:10])
    except (TypeError, ValueError):
        return iso or ""
    return f"{d.day} {MONTHS[d.month - 1]}"


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

def action_badges(its: list[dict]) -> str:
    """«📦 Pedido creado · ⏰ Recordatorio 22 oct · ✉ Comunicado» con las acciones de una alerta."""
    out = []
    orders = [x for x in its if x["kind"] == "order"]
    rems = [x for x in its if x["kind"] == "reminder"]
    if orders:
        pend = [x for x in orders if x["status"] != "hecho"]
        out.append(f"📦 {len(pend)} pedidos creados" if len(pend) > 1 else "📦 Pedido creado" if pend
                   else "📦 Pedido hecho")
    if rems:
        pend = sorted((x for x in rems if x["status"] != "hecho"), key=lambda x: x["due"])
        out.append(f"⏰ Recordatorio {day_es(pend[0]['due'])}" if pend else "⏰ Recordatorio hecho")
    if any(x["kind"] == "comm" for x in its):
        out.append("✉ Comunicado")
    return f'<span class="acts">{esc(" · ".join(out))}</span>' if out else ""


def queue_item(a: Alert, selected: bool, verdict: str | None, its: list[dict] | None = None,
               new: bool = False) -> str:
    text, color = status_chip(a)
    if verdict == "falsa_alarma":
        text, color = "FALSA ALARMA · DESCARTADA", "grey"
    chips = f'<span class="chip {color}">{text}</span>'
    if new:
        chips = '<span class="chip purple">● NUEVA</span>' + chips
    if verdict and verdict != "falsa_alarma":
        chips += f'<span class="chip green">✓ {esc(feedback.VERDICTS[verdict]).upper()}</span>'
    est = '<span class="e"> estimado</span>' if a.estimated and a.worst.inventory_days is not None else ""
    m_txt = f"{signed(a.margin)} d" if a.worst.inventory_days is not None else "sin stock"
    prod = product_es(a.products[0]) if a.products else "sin medicamentos asociados"
    cls = "qitem" + (" sel" if selected else "") + (" new" if new else "") + (
        " off" if verdict == "falsa_alarma" else " done" if verdict else "")
    return (f'<div class="{cls}"><span class="top"><span class="chips">{chips}</span>'
            f'<span class="num m" style="color:{margin_color(a.margin, a.level)}">{m_txt}{est}</span></span>'
            f'<span><span class="n">{esc(a.supplier.name)}</span><span class="w">{esc(a.place)} · '
            f'{esc(a.what_short)}</span></span>'
            f'<span class="a">Afecta a <strong>{esc(prod)}</strong> · {esc(a.affects_note)}</span>'
            f'{action_badges(its or [])}</div>')


def queue(split: str, b: Board, sel: str, its: list[dict]) -> None:
    with st.container(key="panel-queue"):
        md('<div class="card-head"><h2 class="h2" id="cola-t">Requiere tu decisión</h2>'
           '<span class="sub">Por días de margen · pulsa una alerta para abrirla</span></div>')
        if not b.queue:
            md('<p class="sub">Nada pendiente: no hay alertas críticas ni en riesgo latente.</p>')
        for a in b.queue:
            with st.container(key=f"qcard-{a.id}"):
                md(queue_item(a, a.id == sel, b.verdict(a), [x for x in its if x["news_id"] == a.id],
                              new=a.id == st.session_state.get("demo_new")))
                st.button(f"Abrir la alerta de {a.supplier.name}", key=f"qbtn-{a.id}", on_click=_open,
                          args=(split, a.id))
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
                    if a.id == st.session_state.get("demo_new"):
                        tag = ' · <span class="chip purple">● NUEVA</span>' + tag
                    off = ";text-decoration:line-through;opacity:.6" if v == "falsa_alarma" else ""
                    md(f'<div class="qrow"{sel_style}><span><strong>{esc(a.supplier.name)}</strong>{tag}'
                       f'<span class="w" style="display:block">{esc(a.place)} · {esc(a.what_short)}</span></span>'
                       f'<span class="num" style="color:{margin_color(a.margin, a.level)};font-weight:600{off}">'
                       f'{m_txt}</span></div>')
                    st.button(f"Abrir la alerta de {a.supplier.name}", key=f"qbtn-{a.id}", on_click=_open,
                              args=(split, a.id))


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
        why = f' Motivo: «{esc(verdict["note"])}».' if verdict.get("note") else ""
        return (f'<div class="decided fa">{T.ICON_WARN}Falsa alarma <span class="w">{who}.{why} No cuenta en los '
                'indicadores, el calendario, el mapa ni el treemap.</span></div>')
    return (f'<div class="decided ok">{T.ICON_CHECK}✓ {esc(feedback.VERDICTS[v])} <span class="w">{who}. Sigue '
            'en el calendario y el mapa: el riesgo no ha pasado.</span></div>')


def _plan(a: Alert) -> str:
    steps = plan_steps(a.worst, a.supplier, urgent=a.level == "critica")
    return ('<div style="display:flex;flex-direction:column;gap:10px"><h3 class="h3">Plan recomendado</h3>'
            '<ol class="steps">' + "".join(
                f'<li><span class="num i">{i}</span><span class="b"><span class="x">{esc(st_.text)}</span>'
                f'<span class="o">{esc(st_.owner)} · {esc(st_.when)}</span></span></li>'
                for i, st_ in enumerate(steps, 1)) + "</ol></div>")


def decision_controls(split: str, a: Alert, verdict: dict | None, where: str = "") -> None:
    """Aprobar plan · Falsa alarma (con motivo opcional) · Reabrir, en el detalle (where="") y en la
    ventana de la alerta (where="dlg-"): el mismo botón en dos sitios necesita dos claves. Cada botón
    guarda y vuelve a ejecutar la página (decide)."""
    k = f"{split}-{a.id}"
    if verdict:
        c1, c2 = st.columns([3.8, 1.2], vertical_alignment="center")
        c1.markdown(_decided(verdict), unsafe_allow_html=True)
        if c2.button("Reabrir", key=f"{where}re-{k}", width="stretch",
                     help="Vuelve a dejar la alerta pendiente (la auditoría conserva las dos decisiones)"):
            decide(split, a, "reabierta")
        return
    c1, c2 = st.columns(2, vertical_alignment="top")
    with c1.popover("Falsa alarma", width="stretch", key=f"{where}fapop-{k}"):
        md('<p class="sub" style="max-width:340px">La alerta deja de contar en los indicadores, el calendario, '
           'el mapa y el treemap. Se puede reabrir.</p>')
        note = st.text_input("Motivo (opcional)", key=f"{where}fanote-{k}",
                             placeholder="p. ej. el proveedor confirma que la planta no está afectada")
        if st.button("Marcar como falsa alarma", key=f"{where}fa-{k}", width="stretch"):
            decide(split, a, "falsa_alarma", note)
    if c2.button("Aprobar plan", key=f"{where}ok-{k}", type="primary", width="stretch"):
        decide(split, a, "plan_aprobado")


def detail(split: str, a: Alert, verdict: dict | None, its: list[dict]) -> None:
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
        md(_plan(a))
        with st.container(key="decision"):
            md(_trust(a) + action_badges(its))
            decision_controls(split, a, verdict)
            st.button("Crear pedido o recordatorio", key=f"more-{split}-{a.id}", on_click=_open,
                      args=(split, a.id), width="stretch", type="tertiary",
                      help="Abre la alerta completa: pedido prellenado, recordatorio y decisión")


# ---------------------------------------------------------------------------
# Ventana de la alerta: información + decisión
# ---------------------------------------------------------------------------

def _action_line(x: dict, a: Alert | None) -> str:
    src = f" · alerta de {esc(short_supplier(a.supplier.name))}" if a else ""
    done = f" · hecho el {day_es(x['done_ts'])}" if x["status"] == "hecho" and x.get("done_ts") else ""
    if x["kind"] == "comm":
        what = "Correo al proveedor" if x["channel"] == "correo" else "Nota interna al equipo"
        return (f'<div class="act"><span class="ic" aria-hidden="true">✉</span><span><strong>{what}</strong> · '
                f'{esc(x["subject"])}<span class="w">Marcado como enviado el {day_es(x["ts"])} · '
                f'{"redactado por la IA local" if x["source"] == "ia" else "plantilla"} · no se envía nada{src}'
                '</span></span></div>')
    if x["kind"] == "order":
        qty = f"{x['quantity']:,.0f}".replace(",", ".")
        return (f'<div class="act"><span class="ic" aria-hidden="true">📦</span><span><strong>Pedido: {qty} '
                f'{esc(x["unit"])} de {esc(x["material"])}</strong> a {esc(x["supplier_name"])}<span class="w">'
                f'Para el {day_es(x["needed_by"])} · prioridad {esc(x["priority"].lower())} · '
                f'{esc(tasks.ORDER_STATES[x["status"]])}{done}{src}</span></span></div>')
    return (f'<div class="act"><span class="ic" aria-hidden="true">⏰</span><span><strong>{esc(x["text"])}</strong>'
            f'<span class="w">Recordatorio · {esc(x["owner"] or "sin responsable")} · {day_es(x["due"])}{done}{src}'
            '</span></span></div>')


def order_form(split: str, a: Alert) -> None:
    draft_form(split, a.id, tasks.suggest_order(a.worst, a.supplier, a.level), material_es(a.supplier.material),
               f"{split}-{a.id}")


def draft_form(split: str, news_id: str, d: tasks.OrderDraft, material: str, k: str) -> None:
    """Formulario «Crear pedido» prellenado con una propuesta (OrderDraft). Lo usan la ventana de la alerta y
    la del calendario. Al guardar deja un aviso en session_state[f"made-{k}"] y vuelve a ejecutar la página."""
    names = dict(d.options)
    with st.form(key=f"order-{k}", border=False):
        sid = st.selectbox("Proveedor", list(names), index=list(names).index(d.supplier_id), format_func=names.get,
                           key=f"o-sup-{k}", help="Propuesto por el plan: el alternativo si llega a tiempo")
        mat = st.text_input("Material", value=material, key=f"o-mat-{k}")
        c1, c2 = st.columns(2)
        qty = c1.number_input(f"Cantidad ({d.unit})", min_value=0.0, value=float(d.quantity), step=1.0,
                              format="%.0f", key=f"o-qty-{k}")
        need = c2.date_input("Fecha requerida", value=d.needed_by, format="DD/MM/YYYY", key=f"o-date-{k}",
                             help="El día en que se acaba el stock (hoy si no hay stock de reserva)")
        prio = st.selectbox("Prioridad", tasks.PRIORITIES, index=tasks.PRIORITIES.index(d.priority),
                            key=f"o-prio-{k}")
        md(f'<p class="calc"><strong>Cantidad sugerida.</strong> {esc(d.calc)}</p>')
        sent = st.form_submit_button("Crear pedido", type="primary", width="stretch")
    if sent:
        if qty <= 0:
            st.error("Indica una cantidad mayor que 0.")
            return
        tasks.create_order(split, news_id, sid, names[sid], mat, qty, d.unit, need, prio, d.calc, user=USER,
                           con=cache.db())
        st.session_state[f"made-{k}"] = "📦 Pedido creado · queda como «Pedido pendiente de envío al ERP» (no se envía)"
        st.rerun()        # la ventana sigue abierta, ya con el pedido; la tarjeta y la página, también


def reminder_form(split: str, a: Alert) -> None:
    first = plan_steps(a.worst, a.supplier, urgent=a.level == "critica")[0]
    reminder_fields(split, a.id, first.text, first.owner, date.today() + timedelta(days=WHEN_DAYS.get(first.when, 2)),
                    f"{split}-{a.id}")


def reminder_fields(split: str, news_id: str, text: str, owner: str, due: date, k: str) -> None:
    """Formulario «Crear recordatorio» prellenado (ventana de la alerta y ventana del calendario)."""
    with st.form(key=f"rem-{k}", border=False):
        text = st.text_input("Recordatorio", value=text, key=f"r-text-{k}")
        c1, c2 = st.columns(2)
        owner = c1.text_input("Responsable", value=owner, key=f"r-owner-{k}")
        due = c2.date_input("Fecha", value=due, format="DD/MM/YYYY", key=f"r-date-{k}")
        sent = st.form_submit_button("Crear recordatorio", type="primary", width="stretch")
    if sent:
        if not text.strip():
            st.error("Escribe el texto del recordatorio.")
            return
        tasks.create_reminder(split, news_id, text, owner, due, user=USER, con=cache.db())
        st.session_state[f"made-{k}"] = f"⏰ Recordatorio creado para el {day_es(due.isoformat())}"
        st.rerun()


@st.dialog("Alerta", width="large", on_dismiss=_close)
def alert_dialog(split: str, news_id: str) -> None:
    """La alerta completa. Izquierda: qué pasa, la noticia, el impacto, el calendario de ese medicamento y
    el plan. Derecha: la decisión y las acciones (todo se guarda en SQLite). Crear un pedido o un
    recordatorio vuelve a ejecutar la página con la ventana abierta: la tarjeta y «Acciones en curso» ya
    lo muestran detrás. Una decisión cierra la ventana."""
    b = board(split)
    a = next((x for x in b.alerts if x.id == news_id), None)
    if a is None:
        st.warning("Esta alerta ya no está en el conjunto de noticias.")
        return
    s, k = a.supplier, f"{split}-{a.id}"
    its = [x for x in cache.items(split) if x["news_id"] == a.id]
    info, act = st.columns([7, 5], gap="large")
    with info, st.container(key="dlg-info"):
        text, color = status_chip(a)
        quote, _ = quote_for(a.r)
        md(f'<div style="display:flex;flex-direction:column;gap:6px"><span class="overline">Información</span>'
           f'<span class="chip {color}">{text}</span><h2 class="det-name">{esc(s.name)}</h2>'
           f'<span class="det-sub">{esc(a.place)} · {esc(material_es(s.material))}</span></div>')
        md(f'<div style="display:flex;flex-direction:column;gap:8px"><h3 class="h3">Qué pasa</h3>'
           f'<p class="what">{esc(a.what())}</p><blockquote class="quote">«{quote}»</blockquote></div>')
        md('<div style="display:flex;flex-direction:column;gap:8px"><h3 class="h3">La noticia</h3>'
           f'<div class="news-card">{_news(a)}</div></div>')
        md('<div style="display:flex;flex-direction:column;gap:8px"><h3 class="h3">Impacto</h3>'
           f'{_impact_boxes(a)}</div>')
        md(calendar([a], card=False))
        md(_plan(a))
    with act, st.container(key="dlg-act"):
        md('<span class="overline">Decisión</span>')
        if msg := st.session_state.pop(f"made-{k}", None):
            st.success(msg)
        md(_trust(a))
        # Con key y on_change="rerun" la pestaña activa se recuerda: tras crear un pedido o marcar un envío
        # (la página se vuelve a ejecutar) la ventana sigue en la misma pestaña.
        t_dec, t_ord, t_rem, t_com = st.tabs(["Decidir", "📦 Pedido", "⏰ Recordatorio", "✉ Comunicar"],
                                             key=f"tabs-{k}", on_change="rerun")
        with t_dec:
            decision_controls(split, a, b.verdicts.get(a.id), where="dlg-")
        with t_ord:
            order_form(split, a)
        with t_rem:
            reminder_form(split, a)
        with t_com:
            comms_view.panel(split, a, [x for x in its if x["kind"] == "comm"])
        md('<h3 class="h3">Acciones de esta alerta</h3>' + (
            "".join(_action_line(x, None) for x in its) if its else
            '<p class="sub">Aún no hay pedidos ni recordatorios para esta alerta.</p>'))


def actions_panel(split: str, b: Board, its: list[dict]) -> None:
    """Acciones en curso: pedidos y recordatorios creados desde las alertas, con «Hecho»."""
    by_id = {a.id: a for a in b.alerts}
    pend = [x for x in its if x["status"] != "hecho"]
    done = [x for x in its if x["status"] == "hecho"]
    with st.container(key="panel-actions"):
        md('<div class="card-head"><h2 class="h2" id="acc-t">Acciones en curso</h2>'
           f'<span class="sub">{len(pend)} pendiente{"s" if len(pend) != 1 else ""} · pedidos y recordatorios'
           '</span></div>')
        if not its:
            md('<p class="sub">Aún no hay pedidos ni recordatorios. Se crean desde la ventana de cada alerta.</p>')
        for x in pend:
            with st.container(key=f"act-{x['kind']}-{x['id']}"):
                c1, c2 = st.columns([5, 1.25], vertical_alignment="center")
                c1.markdown(_action_line(x, by_id.get(x["news_id"])), unsafe_allow_html=True)
                c2.button("Hecho", key=f"done-{x['kind']}-{x['id']}", on_click=_done, args=(x["kind"], x["id"]),
                          width="stretch", help="Marcar como hecho")
        if done:
            with st.expander(f"Hechas · {len(done)}"):
                md("".join(_action_line(x, by_id.get(x["news_id"])) for x in done))


@st.fragment
def decision_zone(split: str) -> None:
    """Banner + KPIs + cola, acciones en curso, detalle y mapa: elegir una tarjeta o marcar una acción como
    hecha solo vuelve a ejecutar esta función. Las ventanas (alerta, ficha) se abren al final."""
    if toast := st.session_state.pop("toast", None):
        st.toast(toast[0], icon=toast[1])
    b = board(split)
    its = cache.items(split)
    sel_key = f"sel-{split}"
    ids = [a.id for a in b.alerts]
    if st.session_state.get(sel_key) not in ids:
        st.session_state[sel_key] = (b.pending or b.queue or b.alerts)[0].id if ids else None
    sel = st.session_state[sel_key]
    banner(split, b)
    kpi_row(b)
    if not b.alerts:
        md('<section class="card"><p class="what">No hay ninguna noticia de riesgo en este conjunto.</p></section>')
        return
    left, right = st.columns([5, 7], gap="medium")
    with left:
        queue(split, b, sel, its)
        actions_panel(split, b, its)
    with right:
        a = next(x for x in b.alerts if x.id == sel)
        detail(split, a, b.verdicts.get(sel), [x for x in its if x["news_id"] == sel])
        active = b.active
        where(active, {x.id for x in active if x.level in ("critica", "vigilar")})
    req = st.session_state.get("alert_dialog")
    if req and req[0] == split:
        alert_dialog(*req)
    else:
        sheet.open_requested()        # una sola ventana a la vez


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


def calendar(alerts: list[Alert], card: bool = True) -> str:
    """Calendario de roturas de los próximos HORIZON días. card=False: sin tarjeta, para la ventana de una
    alerta (solo los medicamentos de esa alerta)."""
    rows = calendar_rows(alerts)
    head = ('<div class="card-head"><h2 class="h2" id="cal-t">Calendario de roturas</h2>'
            f'<span class="sub">¿Cuánto aguantamos? Próximos {HORIZON} días por medicamento</span></div>') if card else \
        f'<h3 class="h3">Calendario de {"este medicamento" if len(rows) == 1 else "estos medicamentos"}</h3>'
    if not rows:
        empty = ("Ningún medicamento en riesgo en la cola." if card else
                 "Sin medicamentos con stock afectado: el impacto es directo sobre el servicio.")
        return f'<section class="card">{head}<p class="sub">{empty}</p></section>' if card else \
            f'<div style="display:flex;flex-direction:column;gap:8px">{head}<p class="sub">{empty}</p></div>'
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
    grid = (f'<div class="cal{"" if card else " small"}" role="img" aria-label="Calendario de roturas de {n} '
            f'medicamento{"s" if n != 1 else ""}">{"".join(cells)}</div>')
    if not card:
        return f'<div style="display:flex;flex-direction:column;gap:10px">{head}{legend}{grid}</div>'
    return f'<section class="card">{head}{legend}{grid}</section>'


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
           'pulsa una casilla para ver la ficha</span></div>')
        picked = spend_treemap(states, key="tm-control")
        if picked and picked.startswith(GROUP):
            for cat, tiles in tm_groups(states):
                for tid, _, ids in tiles:
                    if tid == picked:
                        sheet.request_list("Categorías sin alertas" if tid == REST else f"{cat}: otros sin riesgo",
                                           ids)
        elif picked:
            sheet.request(picked)
        md('<span class="legend">' + "".join(f'<span><span class="sw" style="background:{c};border:1px solid '
                                             f'{T.LINE_2}"></span>{esc(t)}</span>'
                                             for t, c, _ in STATES.values())
           + '<span>Las casillas más pequeñas tienen un tamaño mínimo para que quepa el nombre; el gasto real va '
             'escrito en cada una.</span></span>')


def charts(split: str) -> None:
    """Calendario y treemap, a todo el ancho, debajo de la zona de decisión."""
    active = board(split).active
    md(calendar([a for a in active if a.level in ("critica", "vigilar")]))
    spend(active)


def page() -> None:
    split = st.session_state.setdefault("split", "test")
    data = cache.data(split)
    if not data:
        st.warning(f"No hay resultados guardados para «{results.SPLITS[split]}». "
                   f"Genéralos con `python scripts/build_results.py --split {split}`.")
        return
    header(split, data)
    if cache.demo_on():
        demo_view.bar(split)
    decision_zone(split)
    if cache.alerts(split):
        charts(split)
    md('<footer class="foot">Datos del reto (Helixa Pharmaceuticals, empresa ficticia). Toda decisión requiere '
       'aprobación humana y queda registrada.</footer>')
    sheet.open_requested()
    demo_view.open_requested()
