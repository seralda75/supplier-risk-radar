"""Calendario: qué medicamentos tienen stock suficiente, cuáles están en peligro y cuáles se quedan sin stock,
y hasta qué día se puede esperar para pedir (core/order_calendar.py).

Resumen (4 KPIs) · calendario mensual o de 90 días con marcadores (último día para pedir, rotura prevista,
recuperación del proveedor, llegada del alternativo, pedidos y recordatorios guardados) · semáforo de
medicamentos. Usa las alertas activas del conjunto elegido: las descartadas como falsa alarma no cuentan y, en
modo demo, una noticia recibida aparece también aquí.

Rendimiento: el calendario es HTML (st.components.v2, sin iframe) con todos los marcadores de unos meses;
cambiar de mes o de vista lo hace el navegador, sin volver a ejecutar la página. Pulsar un día sí la ejecuta
(abre la ventana del día).
"""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from core import results, tasks
from core.labels import material_es, product_es, short_supplier
from core.order_calendar import STATUS_ES, plan
from core.suppliers import load_suppliers

from . import cache, control
from . import theme as T
from .components import esc, head, kpi, kpis, md, tip

STATUS_COLOR = {"rotura": T.RED, "peligro": T.AMBER, "suficiente": T.GREEN}
STATUS_CHIP = {"rotura": "red", "peligro": "amber", "suficiente": "green"}
# tipo de marcador -> (icono, texto de la leyenda)
KINDS = {"pedir": ("🛒", "Último día para pedir"), "rotura": ("⛔", "Rotura prevista"),
         "vuelve": ("↺", "Se recupera el proveedor"), "llega": ("🚚", "Llega el alternativo"),
         "pedido": ("📦", "Pedido guardado"), "recordatorio": ("⏰", "Recordatorio")}
WINDOW = (-62, 200)           # días (desde hoy) con marcadores: unos meses hacia atrás y hacia delante
SEM_HEIGHT = 814              # px: el alto del calendario de un mes de 5 semanas, con su leyenda
MONTHS_LONG = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()


def long_date(d: date) -> str:
    days = "lunes martes miércoles jueves viernes sábado domingo".split()
    return f"{days[d.weekday()]}, {d.day} de {MONTHS_LONG[d.month - 1]} de {d.year}"


def short(text: str, n: int = 22) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def active_countdowns(split: str):
    """Cuentas atrás de las alertas activas (sin las falsas alarmas; en modo demo, con las noticias recibidas)."""
    b = control.board(split)
    return b, [c for a in b.active for c in [a.worst] + a.others]


def events(mats, its: list[dict], today: date) -> dict[str, list[dict]]:
    """{fecha ISO: [marcador]} de la ventana WINDOW. Cada marcador: k (tipo), i (icono), t (texto corto),
    f (texto completo), id (material, si lo hay)."""
    sup = load_suppliers()
    lo, hi = today + timedelta(days=WINDOW[0]), today + timedelta(days=WINDOW[1])
    out: dict[str, list[dict]] = {}

    def add(d: date | None, k: str, t: str, f: str, mid: str = "") -> None:
        if d and lo <= d <= hi:
            out.setdefault(d.isoformat(), []).append({"k": k, "i": KINDS[k][0], "t": t, "f": f, "id": mid})

    for m in mats:
        # En la casilla: el icono (el tipo, ver la leyenda) y una palabra; el texto completo, en el tooltip
        # y en la ventana del día
        name = material_es(m.material.name)
        word = name.split()[0]
        who = short_supplier(sup[m.supplier_id].name)
        if m.deadline:          # solo los materiales con alerta: el resto se repone con normalidad
            how = (f"{m.lead_days:.0f} d de compra urgente (sin alternativo libre)" if m.urgent_buy else
                   f"{m.lead_days:.0f} d de plazo de {who}")
            calc = f"se acaba el stock el día {m.stock_days:.0f} − {how}"
            if m.late_days:     # ya no llega a tiempo: el marcador va a hoy, que es cuando hay que actuar
                add(today, "pedir", f"hoy {word}", f"{name}: pedir hoy con envío urgente · llegaría {m.late_days} "
                    f"días tarde ({calc})", m.material.id)
            else:
                add(m.deadline, "pedir", word, f"Último día para pedir {name} ({calc})", m.material.id)
        if m.stockout:
            prods = ", ".join(product_es(p) for p in m.material.products)
            add(m.stockout, "rotura", word, f"Rotura prevista de {name}: se acaba el stock ({prods})", m.material.id)
        if m.recovery and m.alert_supplier:
            s = short_supplier(sup[m.alert_supplier].name)
            add(m.recovery, "vuelve", s.split()[0], f"{sup[m.alert_supplier].name} se recupera (según la alerta) · "
                f"{name}", m.material.id)
        if m.alt_arrival:
            add(m.alt_arrival, "llega", who.split()[0],
                f"Llega el primer envío del alternativo {sup[m.supplier_id].name} · {name}", m.material.id)
    for x in its:
        if x["kind"] == "order" and x["status"] != "hecho":
            qty = f"{x['quantity']:,.0f}".replace(",", ".")
            add(date.fromisoformat(x["needed_by"]), "pedido", f"{qty} {x['unit']}",
                f"Pedido de {qty} {x['unit']} de {x['material']} a {x['supplier_name']} · prioridad "
                f"{x['priority'].lower()} · pendiente de envío al ERP")
        elif x["kind"] == "reminder" and x["status"] != "hecho":
            add(date.fromisoformat(x["due"]), "recordatorio", short(x["text"], 14),
                f"Recordatorio: {x['text']} · {x['owner'] or 'sin responsable'}")
    order = list(KINDS)
    for v in out.values():
        v.sort(key=lambda e: order.index(e["k"]))
    return out


# ---------------------------------------------------------------------------
# Componente: calendario mensual / 90 días (la navegación la hace el navegador)
# ---------------------------------------------------------------------------

CSS = f"""
.ocal {{ font-family: 'IBM Plex Sans', system-ui, sans-serif; color: {T.INK}; }}
.oc-head {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px;
  margin-bottom: 12px; }}
.oc-nav {{ display: flex; align-items: center; gap: 8px; }}
.oc-title {{ font-size: 18px; font-weight: 700; min-width: 200px; text-align: center; }}
.oc-btn {{ min-height: 38px; padding: 0 14px; border-radius: 8px; border: 1px solid {T.LINE_2}; background: #FFFFFF;
  font: 600 14px 'IBM Plex Sans', system-ui, sans-serif; color: {T.INK}; cursor: pointer; }}
.oc-btn:hover {{ border-color: {T.PURPLE}; background: {T.PURPLE_SOFT}; }}
.oc-btn:focus-visible, .oc-day:focus-visible {{ outline: 2px solid {T.PURPLE}; outline-offset: 2px; }}
.oc-btn[aria-pressed="true"] {{ background: {T.PURPLE}; border-color: {T.PURPLE}; color: #FFFFFF; }}
.oc-btn:disabled {{ opacity: .35; cursor: default; }}
.oc-grid {{ display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 4px; }}
.oc-dow {{ font-size: 12px; font-weight: 600; letter-spacing: .6px; text-transform: uppercase; color: {T.MUTED};
  padding: 2px 6px; }}
.oc-day {{ min-height: 122px; display: flex; flex-direction: column; align-items: stretch; gap: 3px; padding: 5px 4px;
  border: 1px solid {T.LINE}; border-radius: 8px; background: #FFFFFF; text-align: left; cursor: pointer;
  font: inherit; color: inherit; min-width: 0; }}
.oc-day:hover {{ border-color: {T.PURPLE}; box-shadow: 0 0 0 1px {T.PURPLE}; }}
.oc-day.out {{ background: {T.BG}; color: {T.MUTED}; }}
.oc-day.past .mk {{ opacity: .55; }}
.oc-day.today {{ border: 2px solid {T.PURPLE}; padding: 5px; }}
.oc-day .dn {{ font-size: 13px; font-weight: 600; font-family: 'IBM Plex Mono', ui-monospace, monospace; }}
.oc-day.today .dn::after {{ content: " · hoy"; font-family: 'IBM Plex Sans', sans-serif; color: {T.PURPLE_DEEP}; }}
.mk {{ display: block; font-size: 11.5px; line-height: 1.3; padding: 2px 3px; border-radius: 4px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; letter-spacing: -.1px; }}
.mk.k-pedir {{ background: #F1DDFF; color: {T.PURPLE_DEEP}; }}
.mk.k-rotura {{ background: {T.RED_BG}; color: {T.RED_INK}; font-weight: 600; }}
.mk.k-vuelve {{ background: {T.GREEN_BG}; color: #1D5A37; }}
.mk.k-llega {{ background: #E3F1F7; color: #1F4E63; }}
.mk.k-pedido {{ background: {T.AMBER_BG}; color: {T.AMBER_INK}; }}
.mk.k-recordatorio {{ background: {T.BG}; color: {T.INK_2}; }}
.oc-more {{ font-size: 12px; color: {T.MUTED}; padding: 0 5px; }}
"""

JS = """
export default function (component) {
  const { data, setTriggerValue, parentElement } = component;
  const root = parentElement.querySelector('.ocal');
  if (!root || !data) return;
  // El estado (mes y vista) vive en el propio elemento: se conserva al volver a ejecutarse la página
  const st = root.__st || (root.__st = { month: data.month, view: data.view });
  const MONTHS = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre',
                  'noviembre','diciembre'];
  const SHORT = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
  const DOW = ['lun','mar','mié','jue','vie','sáb','dom'];
  const pad = n => String(n).padStart(2, '0');
  const iso = d => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  const today = new Date(data.today + 'T00:00:00');
  const monday = d => { const x = new Date(d); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; };
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls;
                                   if (text !== undefined) e.textContent = text; return e; };
  const btn = (text, label, fn, pressed) => { const b = el('button', 'oc-btn', text); b.type = 'button';
    b.setAttribute('aria-label', label); if (pressed !== undefined) b.setAttribute('aria-pressed', pressed);
    b.onclick = fn; return b; };
  const [minM, maxM] = [data.min_month, data.max_month];

  function shift(delta) {
    const [y, m] = st.month.split('-').map(Number);
    const d = new Date(y, m - 1 + delta, 1);
    st.month = d.getFullYear() + '-' + pad(d.getMonth() + 1);
    render();
  }

  function render() {
    root.replaceChildren();
    const head = el('div', 'oc-head');
    const nav = el('div', 'oc-nav');
    let start, end, title;
    if (st.view === 'mes') {
      const [y, m] = st.month.split('-').map(Number);
      start = monday(new Date(y, m - 1, 1));
      const last = new Date(y, m, 0);
      end = new Date(last); end.setDate(end.getDate() + (6 - (last.getDay() + 6) % 7));
      title = MONTHS[m - 1][0].toUpperCase() + MONTHS[m - 1].slice(1) + ' ' + y;
      const prev = btn('‹', 'Mes anterior', () => shift(-1)); prev.disabled = st.month <= minM;
      const next = btn('›', 'Mes siguiente', () => shift(1)); next.disabled = st.month >= maxM;
      const t = el('span', 'oc-title', title); t.setAttribute('aria-live', 'polite');
      nav.append(prev, t, next, btn('Hoy', 'Volver al mes actual', () => { st.month = data.month; render(); }));
    } else {
      start = monday(today);
      end = new Date(start); end.setDate(end.getDate() + 13 * 7 - 1);
      title = 'Próximos 90 días · ' + today.getDate() + ' ' + SHORT[today.getMonth()] + ' – ' + end.getDate() + ' ' +
              SHORT[end.getMonth()];
      const t = el('span', 'oc-title', title); t.setAttribute('aria-live', 'polite');
      nav.append(t);
    }
    const views = el('div', 'oc-nav');
    views.append(btn('Mes', 'Vista mensual', () => { st.view = 'mes'; render(); }, st.view === 'mes'),
                 btn('90 días', 'Vista de los próximos 90 días', () => { st.view = '90'; render(); }, st.view === '90'));
    head.append(nav, views);
    root.append(head);
    const grid = el('div', 'oc-grid');
    grid.setAttribute('role', 'grid');
    grid.setAttribute('aria-label', title);
    for (const d of DOW) grid.append(el('span', 'oc-dow', d));
    const [y0, m0] = st.month.split('-').map(Number);
    for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
      const key = iso(d);
      const evs = data.events[key] || [];
      const b = el('button', 'oc-day');
      b.type = 'button';
      if (st.view === 'mes' && (d.getMonth() !== m0 - 1 || d.getFullYear() !== y0)) b.classList.add('out');
      if (key === data.today) b.classList.add('today');
      if (key < data.today) b.classList.add('past');
      const first = st.view === '90' && (d.getDate() === 1 || key === iso(start));
      b.append(el('span', 'dn', d.getDate() + (first ? ' ' + SHORT[d.getMonth()] : '')));
      for (const e of evs.slice(0, 3)) {
        const m = el('span', 'mk k-' + e.k, e.i + ' ' + e.t);
        m.title = e.f;
        b.append(m);
      }
      if (evs.length > 3) b.append(el('span', 'oc-more', '+' + (evs.length - 3) + ' más'));
      b.setAttribute('aria-label', d.getDate() + ' de ' + MONTHS[d.getMonth()] + ': ' +
        (evs.length ? evs.map(e => e.f).join('; ') : 'sin eventos') + '. Pulsa para ver el día.');
      b.onclick = () => setTriggerValue('picked', key);
      grid.append(b);
    }
    root.append(grid);
  }
  render();
}
"""

_component = st.components.v2.component("order_calendar", html='<div class="ocal"></div>', css=CSS, js=JS)


def calendar(evs: dict[str, list[dict]], today: date) -> str | None:
    """Dibuja el calendario y devuelve el día pulsado (ISO) en este clic, o None."""
    lo, hi = today + timedelta(days=WINDOW[0]), today + timedelta(days=WINDOW[1])
    res = _component(data={"today": today.isoformat(), "month": today.strftime("%Y-%m"), "view": "mes",
                           "min_month": lo.strftime("%Y-%m"), "max_month": hi.strftime("%Y-%m"), "events": evs},
                     key="ocal", on_picked_change=lambda: None)
    return res.picked if res is not None else None


# ---------------------------------------------------------------------------
# Página
# ---------------------------------------------------------------------------

def _kpis(meds, mats, today: date) -> None:
    n = {k: sum(m.status == k for m in meds) for k in STATUS_ES}
    due = [m for m in mats if m.deadline and m.days_left <= 7]          # incluye los que hay que pedir ya
    late = [m for m in due if m.late_days]
    names = lambda ms: esc(" · ".join(product_es(m.name).split(" ")[0] for m in ms)) or "ninguno"   # noqa: E731
    kpis([
        kpi("Stock suficiente", str(n["suficiente"]), unit=f"de {len(meds)}", color=T.GREEN if n["suficiente"] else "",
            sub=f"medicamentos · {names([m for m in meds if m.status == 'suficiente'])}"),
        kpi("En peligro", str(n["peligro"]), unit=f"de {len(meds)}", color=T.AMBER if n["peligro"] else "",
            sub=f"medicamentos · {names([m for m in meds if m.status == 'peligro'])}"),
        kpi("Rotura prevista", str(n["rotura"]), unit=f"de {len(meds)}", color=T.RED if n["rotura"] else "",
            alert=bool(n["rotura"]), sub=f"medicamentos · {names([m for m in meds if m.status == 'rotura'])}"),
        kpi("Pedidos que vencen en 7 días", str(len(due)), unit="materiales", color=T.RED if late else "",
            sub=(esc(", ".join(material_es(m.material.name) for m in due[:3])) or
                 f"ninguno · {sum(m.deadline is not None for m in mats)} materiales con alerta y fecha límite")
            + (f" · {len(late)} para pedir hoy con envío urgente" if late else "")),
    ])


def _deadline_text(m) -> str:
    """Cuándo pedir un material con alerta (o la frase de reposición regular si no la tiene)."""
    if m.deadline is None:
        return "reposición regular" if not m.affected else "no hace falta: el proveedor vuelve antes"
    if m.late_days:
        return f"Pedir hoy con envío urgente · llegaría {m.late_days} días tarde"
    return "hoy" if m.days_left == 0 else f"en {m.days_left} d"


def semaphore(meds, today: date) -> None:
    # Misma altura que el calendario del mes (la lista se desplaza dentro): sin huecos al lado del calendario
    with st.container(key="panel-semaforo", height=SEM_HEIGHT):
        md(head("Semáforo de medicamentos", "El peor de sus materiales. Sin alerta, la cobertura es solo "
                "informativa: se asume reposición regular."))
        for i, d in enumerate(meds):
            with st.container(key=f"sem-{i}"):
                md(sem_card(d, today))
                # Abre la ventana de hoy con el pedido del material que decide el estado
                st.button("Crear pedido", key=f"sem-order-{i}", on_click=_open_day,
                          args=(today.isoformat(), d.worst.material.id, "📦 Crear pedido"),
                          help=f"Pedido de {material_es(d.worst.material.name)} (el material que decide el estado)")


def sem_card(d, today: date) -> str:
    """Tarjeta de un medicamento: estado, días de stock, fecha límite para pedir y días hasta la rotura.
    Sin alerta: la cobertura (informativa, sin alarma) y «reposición regular»."""
    w, rot, dp = d.worst, d.stockout_days, d.deadline_plan
    if dp:
        stock = f'<span class="l">Stock</span><b class="num">{dp.stock_days:.0f} d</b>'
        when = (f'<span class="l">Pedir antes del</span><b title="{esc(_deadline_text(dp))}">'
                f'{"hoy" if dp.late_days else control.day_es(dp.deadline.isoformat())}</b>')
    else:
        stock = f'<span class="l">Cobertura</span><b class="num muted">{d.cover_days:.0f} d</b>'
        when = '<span class="l">Reposición</span><b class="muted">regular</b>'
    return (f'<div class="sem {d.status}" title="{esc(material_es(w.material.name))}: {esc(w.why)}">'
            f'<span class="top"><span class="n">{esc(product_es(d.name))}</span>'
            f'<span class="chip {STATUS_CHIP[d.status]}">{STATUS_ES[d.status].upper()}</span></span>'
            f'<span class="g"><span>{stock}</span><span>{when}</span>'
            f'<span><span class="l">Rotura</span><b>{"en " + str(rot) + " d" if rot is not None else "no prevista"}'
            f'</b></span></span></div>')


# ---------------------------------------------------------------------------
# Ventana de un día (o «Crear pedido» del semáforo): eventos + crear pedido o recordatorio
# ---------------------------------------------------------------------------

def _open_day(iso: str, mid: str | None = None, tab: str | None = None) -> None:
    """Abre la ventana del día (sigue abierta aunque la página se vuelva a ejecutar, hasta cerrarla)."""
    st.session_state["cal_day"] = (iso, mid)
    if tab:
        st.session_state[f"cal-tabs-{iso}"] = tab


def _close_day() -> None:
    st.session_state.pop("cal_day", None)


def _news_id(b, mp) -> str:
    """La alerta a la que se asocia un pedido o recordatorio del calendario (sale también en su tarjeta);
    si el material no tiene alerta activa, un identificador propio del calendario."""
    if mp.alert_supplier:
        for a in b.active:
            if mp.alert_supplier in {c.supplier_id for c in [a.worst] + a.others}:
                return a.id
    return f"cal-{mp.material.id}"


@st.dialog("Calendario", width="large", on_dismiss=_close_day)
def day_dialog(split: str, iso: str, mid: str | None) -> None:
    today = date.today()
    d = date.fromisoformat(iso)
    b, cds = active_countdowns(split)
    mats, _ = plan(cds, today)
    by = {m.material.id: m for m in mats}
    evs = events(mats, cache.items(split), today).get(iso, [])
    title = long_date(d)
    md(f'<h2 class="det-name">{esc(title[0].upper() + title[1:])}</h2>')
    left, right = st.columns([5, 6], gap="large")
    with left:
        md('<h3 class="h3">Eventos del día</h3>' + ("".join(
            f'<div class="act"><span class="ic" aria-hidden="true">{e["i"]}</span><span>'
            f'<strong>{esc(KINDS[e["k"]][1])}</strong><span class="w">{esc(e["f"])}</span></span></div>'
            for e in evs) if evs else '<p class="sub">Sin eventos este día.</p>'))
    with right, st.container(key="cal-act"):
        ids = list(dict.fromkeys([x for x in [mid] + [e["id"] for e in evs] if x] + [m.material.id for m in mats]))
        mid = st.selectbox("Material", ids, key=f"cal-mat-{iso}-{ids[0]}",
                           format_func=lambda i: f"{material_es(by[i].material.name)} · "
                                                 f"{STATUS_ES[by[i].status].lower()}")
        mp = by[mid]
        k = f"cal-{iso}-{mid}"
        if msg := st.session_state.pop(f"made-{k}", None):
            st.success(msg)
        if mp.deadline is None:
            when = f"Pedir: {_deadline_text(mp)}."
        elif mp.late_days:
            when = f"{_deadline_text(mp)}."
        else:
            when = f"Pedir antes del {control.day_es(mp.deadline.isoformat())} ({_deadline_text(mp)})."
        md(f'<p class="sub" title="{esc(mp.why[0].upper() + mp.why[1:])}">{esc(when)}</p>')
        news_id = _news_id(b, mp)
        t_ord, t_rem = st.tabs(["📦 Crear pedido", "⏰ Crear recordatorio"], key=f"cal-tabs-{iso}", on_change="rerun")
        with t_ord:
            control.draft_form(split, news_id, tasks.suggest_restock(mp, today), material_es(mp.material.name), k)
        with t_rem:
            who = short_supplier(load_suppliers()[mp.supplier_id].name)
            control.reminder_fields(split, news_id, f"Revisar el stock de {material_es(mp.material.name)} con {who}",
                                    "Compras", max(d, today), k)


def page() -> None:
    split = st.session_state.setdefault("split", "test")
    today = date.today()
    if not cache.data(split):
        st.warning(f"No hay resultados guardados para «{results.SPLITS[split]}».")
        return
    b, cds = active_countdowns(split)
    mats, meds = plan(cds, today)
    dismissed = len(b.alerts) - len(b.active)
    note = (f"Proyección desde hoy ({today.day} de {MONTHS_LONG[today.month - 1]} de {today.year}); se asume "
            f"reposición regular salvo los proveedores con alerta. Cuentan las {len(b.active)} alertas activas"
            f"{f' ({dismissed} descartadas como falsa alarma no cuentan)' if dismissed else ''}. Para los materiales "
            "con alerta, la fecha límite para pedir es el día en que se acaba el stock menos el plazo del alternativo "
            "(o de una compra urgente si no lo hay).")
    md(f'<h1 class="h1">Calendario{tip(note)}</h1>')
    _kpis(meds, mats, today)
    left, right = st.columns([7.4, 4.6], gap="medium")
    with left, st.container(key="panel-calendar"):
        picked = calendar(events(mats, cache.items(split), today), today)
        md('<span class="legend">' + "".join(f'<span>{i} {esc(t)}</span>' for i, t in KINDS.values()) + "</span>")
    with right:
        semaphore(meds, today)
    if picked:
        _open_day(picked)
    if req := st.session_state.get("cal_day"):
        day_dialog(split, *req)
