"""Modo demo en el centro de control: barra con «Simular noticia entrante» y «Reiniciar demo», y la
ventana que enseña paso a paso lo que hace el sistema con la noticia (core/demo.py):

    noticia recibida → proveedores candidatos → diagnóstico → cuenta atrás → alerta

Cada paso se queda a la vista STEP_S segundos para que el público lo siga. El diagnóstico es el pipeline
real (assess) en segundo plano, con un contador mientras la IA local trabaja. Al terminar, la ventana se
cierra y la alerta aparece resaltada en la cola, con KPIs, calendario, mapa y treemap actualizados.
"""
from __future__ import annotations

import os
import time

import streamlit as st

from core import demo
from core.countdown import Countdown
from core.labels import CITY_ES, COUNTRY_ES, ZONE_ES, product_es, short_supplier
from core.matching import find_candidates
from core.schemas import EVENT_LABELS_ES
from core.suppliers import load_suppliers

from . import cache
from .components import esc
from .data import build_alerts, signed, status_chip

STEP_S = float(os.getenv("DEMO_STEP_S", "1.6"))      # tiempo mínimo a la vista de cada paso
END_S = float(os.getenv("DEMO_END_S", "2.0"))        # el resultado final, antes de cerrar la ventana
STEPS = ["Noticia recibida", "Proveedores candidatos", "Diagnóstico", "Cuenta atrás", "Alerta"]


def bar(split: str) -> None:
    """Barra del modo demo (encima de la zona de decisión)."""
    con = cache.db()
    done, total = demo.progress(con)
    with st.container(key="demo-bar"):
        c1, c2, c3 = st.columns([4.2, 1.6, 1.1], vertical_alignment="center")
        if split != demo.SPLIT:
            c1.markdown('<div class="demo-t"><b>MODO DEMO</b> · cambia a «Noticias de test (entrega)» para '
                        'simular noticias</div>', unsafe_allow_html=True)
            return
        live = "IA local en directo" if st.session_state.get("demo_live", True) else "IA local con caché"
        up = cache.llm_up()
        c1.markdown(f'<div class="demo-t"><b>MODO DEMO</b> · {done} de {total} noticias del guion · '
                    f'{live if up else "IA apagada: resultados precalculados"} · base de datos aparte '
                    '(demo.db)</div>', unsafe_allow_html=True)
        if c2.button("Simular noticia entrante", key="demo-go", type="primary", width="stretch",
                     disabled=done >= total, help="Procesa la siguiente noticia del guion con el pipeline real"):
            st.session_state.pop("alert_dialog", None)       # una sola ventana a la vez
            st.session_state["demo_run"] = True
        if c3.button("Reiniciar demo", key="demo-reset", width="stretch",
                     help="Borra lo hecho en la demo (decisiones, pedidos, recordatorios, comunicaciones y "
                          "noticias recibidas). No toca data/app.db ni los resultados"):
            demo.reset(con)
            for k in ("demo_new", "alert_dialog", f"sel-{split}"):
                st.session_state.pop(k, None)
            st.session_state["toast"] = ("Demo reiniciada: todo como al principio", "🔄")
            st.rerun()


def open_requested() -> None:
    """Al final de la página: si se ha pulsado «Simular noticia entrante», abre la ventana del proceso."""
    if st.session_state.pop("demo_run", False):
        _incoming()


# ---------------------------------------------------------------------------
# La ventana paso a paso
# ---------------------------------------------------------------------------

def _stepper(state: list[str], body: dict[int, str]) -> str:
    """state[i]: "todo" | "now" | "done"; body[i]: lo que ha encontrado ese paso."""
    rows = []
    for i, (name, stt) in enumerate(zip(STEPS, state)):
        mark = "✓" if stt == "done" else str(i + 1)
        rows.append(f'<li class="ds {stt}"><span class="dn">{mark}</span><div class="db"><span class="dt">'
                    f'{name}</span>{body.get(i, "")}</div></li>')
    return '<ol class="dsteps" aria-live="polite">' + "".join(rows) + "</ol>"


def _news_html(n: dict) -> str:
    return (f'<span class="sub">{esc(n.get("Source") or "")} · {esc(str(n.get("Published_Date") or "")[:10])} · '
            f'{esc(n["News_ID"])}</span><span class="hl">{esc(n["Headline"])}</span>'
            f'<span class="sm">{esc(n.get("Summary") or "")}</span>')


def why(reasons) -> str:
    """Motivos de un candidato en lenguaje de negocio: «nombre citado», «ciudad: Oslo», «país: Alemania»."""
    out = []
    for r in reasons:
        alias = r.alias.strip("'")
        if r.kind == "name":
            out.append({"full": "nombre citado", "fuzzy": "nombre parecido"}.get(r.level, "nombre ambiguo"))
        elif r.kind == "location":
            name = {"city": CITY_ES, "region": ZONE_ES, "river": ZONE_ES}.get(r.level, COUNTRY_ES).get(alias, alias)
            out.append(f"{ {'city': 'ciudad', 'region': 'región', 'river': 'río'}.get(r.level, 'país')}: {name}")
        elif r.kind == "route":
            out.append(f"ruta: {alias}")
        else:
            out.append(f"{'material' if r.kind == 'material' else 'categoría'}: {alias}")
    return ", ".join(dict.fromkeys(out))


def _cands_html(cands: list[dict]) -> str:
    if not cands:
        return '<span class="sm">Ningún proveedor relacionado: la noticia se descarta sin llamar a la IA.</span>'
    more = f'<span class="how">y {len(cands) - 6} más</span>' if len(cands) > 6 else ""
    return '<span class="chips">' + "".join(
        f'<span class="chip grey">{esc(c["name"])} · {esc(c["why"])}</span>' for c in cands[:6]) + "</span>" + more


def _diag_html(r: dict, how: str) -> str:
    sup = load_suppliers()
    if not r["is_risk"]:
        verdict = "<b>Sin riesgo para el suministro</b>"
        if r["affected_ids"]:
            verdict += " (noticia positiva o neutra sobre " + esc(", ".join(
                short_supplier(sup[i].name) for i in r["affected_ids"])) + ")"
    else:
        names = ", ".join(short_supplier(sup[i].name) for i in r["affected_ids"])
        verdict = (f'<b>Riesgo</b> · {esc(EVENT_LABELS_ES.get(r["event_type"], r["event_type"]))} · afecta a '
                   f'<b>{esc(names)}</b> · {"<b>urgente</b>" if r["urgent"] else "no urgente"}')
    return f'<span class="sm">{verdict}</span><span class="how">{esc(how)}</span>'


def _countdown_html(r: dict) -> str:
    sup = load_suppliers()
    if not r["is_risk"] or not r.get("countdown"):
        return '<span class="sm">No hace falta: no hay riesgo.</span>'
    lines = []
    for d in r["countdown"]:
        c = Countdown(**d)
        name = short_supplier(sup[c.supplier_id].name)
        if c.inventory_days is None:
            lines.append(f"<b>{esc(name)}</b>: sin stock de reserva, impacto inmediato durante {c.ttr_days} días")
        else:
            prods = ", ".join(product_es(p) for p in c.products) or "sin medicamentos asociados"
            lines.append(f"<b>{esc(name)}</b>: {c.inventory_days:.0f} d de stock frente a {c.ttr_days} d de "
                         f"recuperación{' (estimada)' if c.ttr_estimated else ''} → margen "
                         f"<b>{signed(c.margin_days)} d</b> · {esc(prods)}")
    return '<span class="sm">' + "<br>".join(lines) + "</span>"


def _alert_html(r: dict) -> tuple[str, str | None]:
    alerts = build_alerts([r])
    if not alerts:
        return ('<span class="sm"><b>No se genera alerta</b>: el sistema filtra el ruido y no molesta al equipo.'
                '</span>', None)
    a = alerts[0]
    text, color = status_chip(a)
    where = ("entra en «Requiere tu decisión»" if a.level in ("critica", "vigilar")
             else "va al informe semanal («En seguimiento semanal»)")
    return f'<span class="chip {color}">{text}</span><span class="sm">{where}</span>', a.id


def _telegram(result: dict, con) -> str:
    """Avisa por Telegram a los compradores suscritos (el envío va en segundo plano). Nunca rompe la demo."""
    try:
        from bot import notifier
        rep = notifier.notify_result(result, demo.SPLIT, True, con)
    except Exception as ex:                 # sin dependencias del bot, base bloqueada…
        return f"Telegram desactivado ({type(ex).__name__})"
    return rep.text() if rep else ""


@st.dialog("Noticia entrante", width="large")
def _incoming() -> None:
    con = cache.db()
    news = demo.next_news(con)
    if news is None:
        st.info("Se han usado todas las noticias del guion. Pulsa «Reiniciar demo» para empezar de nuevo.")
        return
    up = cache.llm_up()
    live = st.session_state.get("demo_live", True)
    state, body = ["todo"] * 5, {}
    ph = st.empty()

    def show(i: int, stt: str = "done", html: str | None = None) -> None:
        state[i] = stt
        if html is not None:
            body[i] = html
        ph.markdown(_stepper(state, body), unsafe_allow_html=True)

    t0 = time.perf_counter()
    # 1. Noticia recibida
    show(0, "done", _news_html(news))
    time.sleep(STEP_S)
    # 2. Candidatos (reglas: nombre, ubicación y categoría); en paralelo arranca el diagnóstico
    future = demo.start(news, live) if up else None
    cands = [{"id": c.id, "name": short_supplier(c.supplier.name), "why": why(c.reasons)}
             for c in find_candidates(news["Headline"], news.get("Summary") or "")]
    show(1, "done", _cands_html(cands))
    time.sleep(STEP_S)
    # 3. Diagnóstico: el pipeline real, con un contador mientras trabaja la IA
    t_llm = time.perf_counter()
    result, mode = None, "precalculado"
    if future is not None:
        while not future.done() and time.perf_counter() - t_llm < demo.LIVE_TIMEOUT_S:
            show(2, "now", f'<span class="sm">La IA local ({"en directo" if live else "con caché"}) está leyendo '
                           f'la noticia y los proveedores candidatos… <b class="num">'
                           f'{time.perf_counter() - t_llm:.0f} s</b></span>')
            time.sleep(0.25)
        if future.done() and future.exception() is None:
            result, mode = future.result(), ("ia_directo" if live else "ia_cache")
    if result is None:
        result = demo.precomputed(news["News_ID"])
    secs = time.perf_counter() - t_llm
    how = {"ia_directo": f"IA local qwen2.5:7b en directo + reglas · {secs:.1f} s",
           "ia_cache": f"IA local qwen2.5:7b (respuesta en caché) + reglas · {secs:.1f} s",
           "precalculado": "Resultado precalculado del mismo pipeline" +
                           (" (la IA tardaba demasiado)" if up else " (IA local apagada)")}[mode]
    if result.get("mode") == "reglas" and mode != "precalculado":
        how = "Reglas: sin candidatos no hace falta llamar a la IA"
    show(2, "done", _diag_html(result, how))
    time.sleep(max(0.0, STEP_S - 0.5))
    # 4. Cuenta atrás y 5. alerta
    show(3, "done", _countdown_html(result))
    time.sleep(STEP_S)
    html, alert_id = _alert_html(result)
    demo.save(con, result, mode, secs)
    tg = _telegram(result, con)
    show(4, "done", html + (f'<span class="sm">📱 {esc(tg)}</span>' if tg else ""))
    st.session_state["demo_last"] = {"news_id": news["News_ID"], "mode": mode, "pipeline_s": round(secs, 2),
                                     "total_s": round(time.perf_counter() - t0, 2)}
    if alert_id:
        st.session_state["demo_new"] = alert_id
        st.session_state[f"sel-{demo.SPLIT}"] = alert_id
    time.sleep(END_S)
    st.rerun()                     # cierra la ventana: la alerta aparece en la cola, resaltada
