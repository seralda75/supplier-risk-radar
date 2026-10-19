"""Panel Supplier Risk Radar (Streamlit).

    streamlit run app.py

Lee los resultados guardados (data/results/*.json, generados con scripts/build_results.py): al abrir
la app no se llama al LLM, así que arranca en segundos y funciona sin GPU. Las respuestas de los
compradores (confirmar / falsa alarma) se guardan en SQLite (core/feedback.py).

Pestañas: Alertas · Mapa · Proveedor · ¿Y si…? · Transparencia. El simulador «¿Y si…?» es lo único
que puede llamar al LLM, y solo cuando el usuario pulsa «Interpretar» (los ejemplos ya están interpretados).
"""
from __future__ import annotations

import html
import math
import re
from collections import defaultdict

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import feedback, llm, results, scenario
from core.config import ROOT
from core.countdown import MARGIN_TIGHT_DAYS
from core.geo import coords
from core.schemas import EVENT_LABELS_ES
from core.suppliers import CITY_GEO, COUNTRY_ALIASES, MATERIAL_ALIASES, SUPPLIER_ROUTES, load_suppliers
from core.urgency import dependency

st.set_page_config(page_title="Supplier Risk Radar · Helixa", page_icon="📡", layout="wide")

# ---------------------------------------------------------------------------
# Estilo
# ---------------------------------------------------------------------------
PURPLE, PURPLE_DARK, INK, MUTED = "#A100FF", "#460073", "#1C1A22", "#6B6675"
STATUS = {   # estado de la cuenta atrás -> (etiqueta, color)
    "rotura_prevista": ("Rotura prevista", "#C8102E"),
    "riesgo_latente": ("Riesgo latente", "#E35205"),
    "margen_ajustado": ("Margen ajustado", "#D99A00"),
    "cubierto": ("Cubierto", "#2E8540"),
    "sin_inventario": ("Sin inventario de reserva", "#5F5A66"),
}
STATUS_ORDER = list(STATUS)
REVIEW_REASONS = {"sin_consenso": "reglas y LLM no coinciden", "confianza_baja": "confianza baja"}

st.markdown(f"""
<style>
  .block-container {{ padding-top: 3.2rem; max-width: 1280px; }}
  h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}
  .brand {{ display:flex; align-items:baseline; gap:.6rem; margin-bottom:.2rem; }}
  .brand .chev {{ color:{PURPLE}; font-weight:800; font-size:2rem; line-height:1; }}
  .brand .title {{ font-size:1.9rem; font-weight:700; color:{INK}; }}
  .subtitle {{ color:{MUTED}; margin-bottom:1rem; }}
  .badge {{ display:inline-block; padding:.12rem .55rem; border-radius:999px; font-size:.74rem;
           font-weight:600; margin-right:.35rem; white-space:nowrap; }}
  .card-head {{ display:flex; flex-wrap:wrap; align-items:center; gap:.2rem; margin-bottom:.35rem; }}
  .headline {{ font-size:1.08rem; font-weight:650; color:{INK}; margin:.1rem 0 .15rem 0; }}
  .meta {{ color:{MUTED}; font-size:.8rem; }}
  .sup-row {{ display:grid; grid-template-columns: 2.1fr 1fr 1.25fr 1fr; gap:.6rem;
             padding:.6rem 0; border-top:1px solid #EEE9F3; }}
  @media (max-width: 760px) {{ .sup-row {{ grid-template-columns: 1fr 1fr; }} }}
  .sup-name b {{ color:{INK}; }}
  .muted {{ color:{MUTED}; font-size:.8rem; }}
  .kpi .k {{ display:block; color:{MUTED}; font-size:.7rem; text-transform:uppercase; letter-spacing:.05em; }}
  .kpi .v {{ display:block; font-size:1.25rem; font-weight:700; color:{INK}; }}
  .kpi .s {{ display:block; color:{MUTED}; font-size:.75rem; }}
  .margin {{ border-left:4px solid; padding-left:.6rem; }}
  .products {{ font-size:.82rem; color:{INK}; margin:-.2rem 0 .3rem 0; }}
  .evidence {{ border-left:3px solid {PURPLE}; background:#F8F4FC; padding:.45rem .7rem; margin:.4rem 0;
              font-style:italic; color:#3A3542; font-size:.88rem; }}
  .action {{ font-size:.88rem; color:{INK}; }}
  .stat {{ background:#F6F2FA; border-radius:10px; padding:.7rem .9rem; }}
  .stat .n {{ font-size:1.6rem; font-weight:750; color:{PURPLE_DARK}; }}
  .stat .l {{ font-size:.78rem; color:{MUTED}; }}
  div[data-testid="stTabs"] button[aria-selected="true"] p {{ color:{PURPLE}; font-weight:650; }}
</style>
""", unsafe_allow_html=True)


def badge(text: str, bg: str, fg: str = "#FFFFFF") -> str:
    return f'<span class="badge" style="background:{bg};color:{fg}">{html.escape(text)}</span>'


def outline(text: str, color: str) -> str:
    return (f'<span class="badge" style="background:#FFFFFF;color:{color};border:1px solid {color}">'
            f'{html.escape(text)}</span>')


def days(x: float | None, sign: bool = False) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "—"
    return f"{x:+.0f} d" if sign else f"{x:.0f} d"


def pct(x: float) -> str:
    return "—" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.1%}".replace(".", ",")


# ---------------------------------------------------------------------------
# Datos (solo lectura de resultados guardados; nada de LLM)
# ---------------------------------------------------------------------------

def _mtime(split: str) -> float:
    p = results.path(split)
    return p.stat().st_mtime if p.exists() else 0.0


@st.cache_data(show_spinner=False)
def load_split(split: str, _mtime_key: float) -> dict | None:
    return results.load(split)


def get(split: str) -> dict | None:
    return load_split(split, _mtime(split))


def min_margin(r: dict) -> float:
    cds = r.get("countdown") or []
    return min((c["margin_days"] for c in cds), default=float("inf"))


def worst_status(r: dict) -> str | None:
    cds = r.get("countdown") or []
    if not cds:
        return None
    return min(cds, key=lambda c: (c["margin_days"], STATUS_ORDER.index(c["status"])))["status"]


SUP = load_suppliers()

# ---------------------------------------------------------------------------
# Cabecera y barra lateral
# ---------------------------------------------------------------------------
st.markdown('<div class="brand"><span class="chev">&gt;</span><span class="title">Supplier Risk Radar</span></div>'
            '<div class="subtitle">Helixa Pharmaceuticals · vigilancia de noticias sobre proveedores · '
            '100 % local (Ollama)</div>', unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Conjunto de noticias")
    split = st.radio("Conjunto", list(results.SPLITS), format_func=results.SPLITS.get,
                     label_visibility="collapsed", key="split")
    data = get(split)
    if data:
        res = data["results"]
        mode = "juez LLM " + data["model"] if data["mode"] == "llm" else "solo reglas"
        st.caption(f"{len(res)} noticias · {mode}  \nGenerado: {data['generated'].replace('T', ' ')}")
        if split == "train":
            st.caption("Entrenamiento evaluado *leave-one-out*: cada noticia sin verse a sí misma como ejemplo.")
    st.divider()
    st.caption("La app lee resultados guardados: no llama al LLM al abrirse. Para regenerarlos: "
               "`python scripts/build_results.py`")

if not data:
    st.warning(f"No hay resultados guardados para «{results.SPLITS[split]}». "
               f"Genera los resultados con `python scripts/build_results.py --split {split}`.")
    st.stop()

res = data["results"]
risks = [r for r in res if r["is_risk"]]
verdicts = feedback.latest(split)

tab_alerts, tab_map, tab_sup, tab_whatif, tab_transp = st.tabs(
    ["🚨 Alertas", "🗺️ Mapa", "🏭 Proveedor", "🧪 ¿Y si…?", "🔍 Transparencia"])


# ---------------------------------------------------------------------------
# Alertas
# ---------------------------------------------------------------------------

def save_verdict(split_: str, news_id: str, verdict: str) -> None:
    feedback.save(split_, news_id, verdict, user="comprador (panel)")
    st.toast(f"{news_id}: {feedback.VERDICTS[verdict]} · guardado en la auditoría", icon="✅")


def supplier_row(c: dict, r: dict) -> str:
    s = SUP.get(c["supplier_id"])
    tags = []
    if s:
        tags.append(f"{s.category} · {s.material}")
        tags.append("proveedor único" if s.single_source else f"alternativo {s.alternate_id or '—'}")
    # TTS: de dónde sale
    if c["inventory_days"] is None:
        tts_sub = "sin inventario (servicio o logística)"
    elif c["alternate_margin_days"]:
        tts_sub = f"inventario {days(c['inventory_days'])} + alternativo {days(c['alternate_margin_days'])}"
    else:
        tts_sub = f"inventario {days(c['inventory_days'])}" + (f" · {c['note']}" if c["note"] else "")
    # TTR: noticia o estimado
    if c["ttr_estimated"]:
        ttr_sub = f"estimado · {c['ttr_basis']}"
    else:
        ttr_sub = f"de la noticia: «{r.get('recovery_reported') or c['ttr_days']}»"
    label, color = STATUS[c["status"]]
    margin_val = days(c["margin_days"], sign=True) if c["inventory_days"] is not None else "inmediato"
    if c["inventory_days"] is None and c["ttr_days"] == 0:
        margin_val = "sin corte"
    prods = ", ".join(c["products"]) or "sin productos registrados"
    return (f'<div class="sup-row">'
            f'<div class="sup-name"><b>{html.escape(c["supplier_name"])}</b> '
            f'<span class="muted">{c["supplier_id"]}</span><br>'
            f'<span class="muted">{html.escape(" · ".join(tags))}</span></div>'
            f'<div class="kpi"><span class="k">TTS · aguante</span><span class="v">{days(c["tts_days"])}</span>'
            f'<span class="s">{html.escape(tts_sub)}</span></div>'
            f'<div class="kpi"><span class="k">TTR · recuperación</span><span class="v">{c["ttr_days"]} d</span>'
            f'<span class="s">{html.escape(ttr_sub)}</span></div>'
            f'<div class="kpi margin" style="border-color:{color}"><span class="k">Margen</span>'
            f'<span class="v" style="color:{color}">{margin_val}</span><span class="s">{label}</span></div>'
            f'</div><div class="products">💊 {html.escape(prods)}</div>')


def alert_card(r: dict) -> None:
    with st.container(border=True):
        head = [badge("URGENTE", "#C8102E") if r["urgent"] else badge("No urgente", "#ECE7F1", INK),
                badge(EVENT_LABELS_ES.get(r["event_type"], r["event_type"]), PURPLE_DARK)]
        if r.get("needs_review"):
            why = ", ".join(REVIEW_REASONS.get(x, x) for x in r.get("review_reasons", []))
            head.append(badge(f"⚑ Decisión humana requerida · {why}", PURPLE))
        if any(c["status"] == "riesgo_latente" for c in r["countdown"]):
            estimated = any(c["ttr_estimated"] for c in r["countdown"] if c["status"] == "riesgo_latente")
            head.append(outline("Riesgo latente · TTR " + ("estimado" if estimated else "de la noticia"),
                                STATUS["riesgo_latente"][1]))
        v = verdicts.get(r["news_id"])
        if v:
            head.append(outline(f"{feedback.VERDICTS[v['verdict']]} · {v['ts'][:16].replace('T', ' ')}",
                                "#2E8540" if v["verdict"] == "confirmada" else MUTED))
        st.markdown(
            f'<div class="card-head">{"".join(head)}</div>'
            f'<div class="headline">{html.escape(r["headline"])}</div>'
            f'<div class="meta">{r["news_id"]} · {r.get("published_date", "")[:10]} · '
            f'{html.escape(r.get("source") or "")}</div>'
            + "".join(supplier_row(c, r) for c in r["countdown"])
            + f'<div class="evidence">“{html.escape(r["evidence"])}”</div>'
            f'<div class="action"><b>Acción recomendada.</b> {html.escape(r["action"])}</div>',
            unsafe_allow_html=True)
        cols = st.columns([1.1, 1.1, 4])
        cols[0].button("✅ Confirmar", key=f"ok-{split}-{r['news_id']}", on_click=save_verdict,
                       args=(split, r["news_id"], "confirmada"), width="stretch")
        cols[1].button("✖ Falsa alarma", key=f"fa-{split}-{r['news_id']}", on_click=save_verdict,
                       args=(split, r["news_id"], "falsa_alarma"), width="stretch")
        g = r.get("gold")
        extra = f"Urgencia: {r['urgency_reason']}."
        if g:
            ok = results.is_perfect(r)
            extra += (f"  ·  Etiqueta oficial: Is_Risk {'Y' if g['is_risk'] else 'N'}, Urgent "
                      f"{'Y' if g['urgent'] else 'N'}, IDs {'; '.join(g['affected_ids']) or '—'} "
                      f"{'✔ coincide' if ok else '✘ no coincide'}")
        cols[2].caption(extra)


with tab_alerts:
    review = [r for r in risks if r.get("needs_review")]
    stats = [(len(risks), "alertas (noticias de riesgo)"), (sum(r["urgent"] for r in risks), "urgentes"),
             (sum(worst_status(r) == "rotura_prevista" for r in risks), "con rotura prevista"),
             (sum(any(c["status"] == "riesgo_latente" for c in r["countdown"]) for r in risks), "riesgo latente"),
             (len(review), "alertas que requieren decisión humana")]
    for col, (n, label) in zip(st.columns(len(stats)), stats):
        col.markdown(f'<div class="stat"><div class="n">{n}</div><div class="l">{label}</div></div>',
                     unsafe_allow_html=True)
    st.write("")

    f1, f2, f3, f4 = st.columns([1.1, 1.6, 1.6, 1.1])
    urg = f1.radio("Urgencia", ["Todas", "Urgentes", "No urgentes"], horizontal=False)
    present = [s for s in STATUS_ORDER if any(c["status"] == s for r in risks for c in r["countdown"])]
    st_sel = f2.multiselect("Estado del margen", present, default=present, format_func=lambda s: STATUS[s][0])
    cats = sorted({SUP[c["supplier_id"]].category for r in risks for c in r["countdown"]})
    cat_sel = f3.multiselect("Categoría del proveedor", cats, default=cats)
    only_review = f4.toggle("Solo decisión humana", value=False)

    shown = [r for r in risks
             if (urg == "Todas" or r["urgent"] == (urg == "Urgentes"))
             and any(c["status"] in st_sel for c in r["countdown"])
             and any(SUP[c["supplier_id"]].category in cat_sel for c in r["countdown"])
             and (not only_review or r.get("needs_review"))]
    shown.sort(key=lambda r: (min_margin(r), not r["urgent"]))
    st.caption(f"{len(shown)} de {len(risks)} alertas · ordenadas por margen de días (TTS − TTR), "
               f"de menor a mayor. Margen ajustado: menos de {MARGIN_TIGHT_DAYS} días.")
    for r in shown:
        alert_card(r)
    if not shown:
        st.info("No hay alertas con estos filtros.")

    with st.expander(f"Noticias sin riesgo ({len(res) - len(risks)})"):
        st.caption("Una noticia sin riesgo también puede requerir decisión humana: si las reglas sí ven un "
                   "riesgo, podría ser una alerta perdida.")
        st.dataframe(pd.DataFrame([{"Noticia": r["news_id"], "Titular": r["headline"],
                                    "Proveedores citados": "; ".join(r["affected_ids"]),
                                    "Decisión humana": ", ".join(REVIEW_REASONS.get(x, x)
                                                                 for x in r.get("review_reasons", [])),
                                    "Motivo": r["explanation"]} for r in res if not r["is_risk"]]),
                     hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Mapa
# ---------------------------------------------------------------------------
def exposure_map(exposure: dict[str, dict], calm_hover: str) -> go.Figure:
    """Mapa de proveedores: los expuestos coloreados por margen y todos con tamaño según el gasto.
    exposure: {supplier_id: {"margin": días, "status": estado, "hover": texto extra}}."""
    rows, per_city = [], defaultdict(int)
    max_spend = max(s.annual_spend_eur or 0 for s in SUP.values()) or 1
    for s in SUP.values():
        ll = coords(s.city)
        if not ll:
            continue
        k = per_city[s.city]
        per_city[s.city] += 1
        e = exposure.get(s.id)
        rows.append({"id": s.id, "name": s.name, "city": s.city, "category": s.category,
                     "lat": ll[0] + 0.35 * k, "lon": ll[1] + 0.45 * k,
                     "size": 7 + 26 * math.sqrt((s.annual_spend_eur or 0) / max_spend),
                     "exposed": e is not None, "margin": e["margin"] if e else None,
                     "status": STATUS[e["status"]][0] if e else "", "hover": e["hover"] if e else ""})
    df = pd.DataFrame(rows)
    exp, calm = df[df.exposed], df[~df.exposed]
    fig = go.Figure()
    fig.add_trace(go.Scattergeo(
        lat=calm.lat, lon=calm.lon, mode="markers", name="Sin exposición",
        marker=dict(size=calm["size"], color="#CFC8D8", opacity=.55, line=dict(width=.5, color="#FFFFFF")),
        text=calm.name + " · " + calm.city, hovertemplate=f"%{{text}}<br>{calm_hover}<extra></extra>"))
    lo, hi = -60, 60
    scale = [[0, "#8E0C24"], [.42, "#E35205"], [.5, "#D99A00"],
             [(MARGIN_TIGHT_DAYS - lo) / (hi - lo), "#7BB662"], [1, "#2E8540"]]
    fig.add_trace(go.Scattergeo(
        lat=exp.lat, lon=exp.lon, mode="markers", name="Expuesto",
        marker=dict(size=exp["size"], color=exp.margin.clip(lo, hi), cmin=lo, cmax=hi, colorscale=scale,
                    line=dict(width=1.2, color=PURPLE_DARK), opacity=.92,
                    colorbar=dict(title="Margen<br>(días)", thickness=12, len=.6)),
        customdata=exp[["id", "city", "category", "margin", "status", "hover"]].values,
        text=exp.name,
        hovertemplate=("<b>%{text}</b> (%{customdata[0]})<br>%{customdata[1]} · %{customdata[2]}<br>"
                       "Margen: %{customdata[3]:+.0f} d · %{customdata[4]}<br>%{customdata[5]}<extra></extra>")))
    fig.update_geos(projection_type="natural earth", showland=True, landcolor="#F4F1F7", showocean=True,
                    oceancolor="#FFFFFF", countrycolor="#DDD5E6", coastlinecolor="#CFC6DA", showframe=False,
                    lataxis_range=[-35, 70], lonaxis_range=[-115, 150])
    fig.update_layout(height=540, margin=dict(l=0, r=0, t=10, b=0), legend=dict(orientation="h", y=-.02),
                      paper_bgcolor="#FFFFFF", font=dict(color=INK))
    return fig


def show_map(fig: go.Figure) -> None:
    # El contorno del mundo se sirve desde static/ (no desde cdn.plot.ly): funciona sin internet
    st.plotly_chart(fig, width="stretch", config={"topojsonURL": "app/static/topojson/", "displaylogo": False})


with tab_map:
    exposure: dict[str, dict] = {}
    for r in risks:
        for c in r["countdown"]:
            prev = exposure.get(c["supplier_id"])
            if prev is None or c["margin_days"] < prev["margin"]:
                exposure[c["supplier_id"]] = {"margin": c["margin_days"], "status": c["status"],
                                              "news": r["news_id"], "urgent": "Sí" if r["urgent"] else "No",
                                              "hover": f"Noticia {r['news_id']} · urgente: "
                                                       f"{'Sí' if r['urgent'] else 'No'}"}
    st.markdown(f"**{len(exposure)} proveedores expuestos** en «{results.SPLITS[split]}». "
                "Color: margen de días (rojo = rotura, verde = cubierto). Tamaño: gasto anual.")
    show_map(exposure_map(exposure, "Sin eventos en este conjunto"))
    if exposure:
        st.dataframe(pd.DataFrame([{"ID": i, "Proveedor": SUP[i].name, "Ciudad": SUP[i].city,
                                    "Categoría": SUP[i].category, "Margen (d)": e["margin"],
                                    "Estado": STATUS[e["status"]][0], "Noticia": e["news"], "Urgente": e["urgent"],
                                    "Gasto anual (€)": SUP[i].annual_spend_eur or 0}
                                   for i, e in exposure.items()]).sort_values("Margen (d)"),
                     hide_index=True, width="stretch",
                     column_config={"Gasto anual (€)": st.column_config.NumberColumn(format="%.0f"),
                                    "Margen (d)": st.column_config.NumberColumn(format="%+.0f")})


# ---------------------------------------------------------------------------
# Ficha de proveedor
# ---------------------------------------------------------------------------
with tab_sup:
    ids = sorted(SUP)
    default = min(exposure, key=lambda i: exposure[i]["margin"]) if exposure else ids[0]
    sid = st.selectbox("Proveedor", ids, index=ids.index(default),
                       format_func=lambda i: f"{i} · {SUP[i].name}" + ("  ⚠" if i in exposure else ""))
    s = SUP[sid]
    dep = dependency(s)
    st.markdown(f"### {s.name} <span class='muted'>{s.id}</span>", unsafe_allow_html=True)
    st.markdown(" ".join([badge(s.category, PURPLE_DARK),
                          badge("Proveedor único", "#C8102E") if s.single_source else badge("Con alternativo",
                                                                                              "#2E8540"),
                          outline(f"Criticidad {s.criticality}", PURPLE),
                          outline(f"Dependencia {dep.score:.2f}", PURPLE)]), unsafe_allow_html=True)
    facts = [(s.city, s.country),
             (days(s.inventory_cover_days) if s.inventory_cover_days is not None else "—", "cobertura de inventario"),
             (days(s.lead_time_days) if s.lead_time_days is not None else "—", "plazo de entrega"),
             (f"{(s.annual_spend_eur or 0) / 1e6:.2f} M€".replace(".", ","),
              f"gasto anual · {s.share_of_category_pct or 0:.0f} % de su categoría")]
    st.write("")
    for col, (n, label) in zip(st.columns(4), facts):
        col.markdown(f'<div class="stat"><div class="n">{html.escape(n)}</div>'
                     f'<div class="l">{html.escape(label)}</div></div>', unsafe_allow_html=True)
    st.write("")

    left, right = st.columns([1.1, 1])
    with left:
        st.markdown("**Material y productos**")
        st.markdown(f"- Material: **{s.material}**" + (f" ({', '.join(s.material_ids)}, {s.role})"
                                                       if s.material_ids else ""))
        if s.monthly_requirement:
            st.markdown(f"- Necesidad mensual de Helixa: **{s.monthly_requirement}**")
        st.markdown(f"- Productos que dependen de él: **{', '.join(s.products) or 'ninguno registrado'}**")
        st.markdown(f"- Calidad: {s.quality_score if s.quality_score is not None else '—'}")
        st.markdown("**Factores de dependencia:** " + " · ".join(dep.factors))
    with right:
        st.markdown("**Alternativo aprobado**")
        if s.alternate_id and s.alternate_id in SUP:
            a = SUP[s.alternate_id]
            st.markdown(f"- **{a.name}** ({a.id}) · {a.city}, {a.country}")
            st.markdown(f"- Plazo de entrega: {days(a.lead_time_days)} · inventario: "
                        f"{days(a.inventory_cover_days) if a.inventory_cover_days is not None else '—'}")
            if s.inventory_cover_days is not None and a.lead_time_days is not None:
                if a.lead_time_days >= s.inventory_cover_days:
                    st.warning(f"El alternativo tarda {a.lead_time_days:.0f} días en entregar y el inventario "
                               f"cubre {s.inventory_cover_days:.0f}: **no llega a tiempo** si se corta el suministro.")
                else:
                    st.success(f"El alternativo entrega en {a.lead_time_days:.0f} días, antes de que se acabe "
                               f"el inventario ({s.inventory_cover_days:.0f} días).")
        else:
            st.error("Sin alternativo aprobado: cualquier interrupción afecta directamente a la producción.")

    st.markdown("**Historial de eventos** (todos los conjuntos)")
    hist = []
    for sp in results.SPLITS:
        d = get(sp)
        if not d:
            continue
        fb = feedback.latest(sp)
        for r in d["results"]:
            if sid not in r["affected_ids"]:
                continue
            c = next((x for x in r.get("countdown", []) if x["supplier_id"] == sid), None)
            hist.append({"Fecha": r.get("published_date", "")[:10], "Conjunto": results.SPLITS[sp],
                         "Noticia": r["news_id"], "Titular": r["headline"],
                         "Evento": EVENT_LABELS_ES.get(r["event_type"], r["event_type"]),
                         "Riesgo": "Sí" if r["is_risk"] else "No", "Urgente": "Sí" if r["urgent"] else "No",
                         "Margen (d)": c["margin_days"] if c and c["inventory_days"] is not None else None,
                         "Estado": STATUS[c["status"]][0] if c else "",
                         "Respuesta comprador": feedback.VERDICTS[fb[r["news_id"]]["verdict"]]
                         if r["news_id"] in fb else ""})
    if hist:
        st.dataframe(pd.DataFrame(hist).sort_values("Fecha", ascending=False), hide_index=True,
                     width="stretch",
                     column_config={"Margen (d)": st.column_config.NumberColumn(format="%+.0f")})
    else:
        st.caption("Ninguna noticia de los tres conjuntos afecta a este proveedor.")


# ---------------------------------------------------------------------------
# Simulador «¿Y si…?»
# ---------------------------------------------------------------------------
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


def use_example() -> None:
    ex = EXAMPLES_SC[st.session_state["sc_example"]]
    load_scenario(ex["scenario"], f"Ejemplo precalculado: «{ex['text']}»", ex["dropped"])


def run_interpret() -> None:
    text = st.session_state.get("sc_text", "").strip()
    try:
        sc, dropped = scenario.interpret(text)
    except Exception as e:                      # Ollama caído, tiempo de espera, JSON no válido...
        st.session_state["sc_error"] = f"No se pudo interpretar el escenario: {e}"
        return
    load_scenario(sc, f"Interpretado por el LLM a partir de: «{text}»", dropped)


def with_extra(options: list[str], current: list[str]) -> list[str]:
    return options + [x for x in current if x not in options]


EXAMPLES_SC = scenario.load_examples()

with tab_whatif:
    st.markdown("#### ¿Qué pasaría si…?")
    st.caption("El LLM solo traduce tu pregunta a un escenario estructurado (lugares, categorías, materiales y "
               "duración). Los proveedores afectados, la cuenta atrás y las acciones los calcula el código con el "
               "mismo diccionario geográfico y la misma cuenta atrás que las alertas. Revisa el escenario antes "
               "de calcular.")
    ollama_up = llm.is_up()
    left, right = st.columns([1.3, 1])
    with left:
        st.text_area("Escribe un escenario", key="sc_text", height=90, disabled=not ollama_up,
                     placeholder="¿Y si se inunda Gujarat 3 semanas?")
        st.button("Interpretar con el LLM", on_click=run_interpret, disabled=not ollama_up, type="primary",
                  key="sc_interpret")
        if not ollama_up:
            st.info("Ollama no está disponible: usa los escenarios de ejemplo (ya interpretados). "
                    "Puedes corregirlos a mano; el cálculo no necesita el LLM.")
    with right:
        if EXAMPLES_SC:
            st.selectbox("…o elige un ejemplo", range(len(EXAMPLES_SC)), key="sc_example",
                         format_func=lambda i: EXAMPLES_SC[i]["text"])
            st.button("Usar este ejemplo", on_click=use_example, key="sc_use_example")
        else:
            st.caption("No hay ejemplos precalculados: `python scripts/build_scenarios.py`.")
    if st.session_state.get("sc_error"):
        st.error(st.session_state["sc_error"])

    loaded = st.session_state.get("sc_loaded")
    if loaded:
        sc0 = scenario.Scenario.model_validate(loaded["scenario"])
        v = st.session_state.get("sc_ver", 0)
        with st.form(f"sc_form_{v}"):
            st.markdown("**Escenario interpretado** · revísalo y corrígelo antes de calcular")
            st.caption(loaded["source"])
            if loaded["dropped"]:
                st.caption("Descartado porque no aparece en el texto: " + ", ".join(loaded["dropped"]) + ".")
            c1, c2, c3 = st.columns([1.6, 1.2, .8])
            title = c1.text_input("Título", sc0.title)
            events = list(scenario.SCENARIO_EVENTS)
            event = c2.selectbox("Tipo de evento", events, index=events.index(sc0.event_type),
                                 format_func=lambda e: EVENT_LABELS_ES.get(e, e))
            dur = c3.number_input("Duración (días)", min_value=0, max_value=730, step=1,
                                  value=int(sc0.duration_days or 0),
                                  help="0 = sin indicar: se usa el valor por defecto del tipo de evento (estimado)")
            c1, c2, c3 = st.columns(3)
            countries = c1.multiselect("Países", with_extra(SC_COUNTRIES, sc0.countries), sc0.countries,
                                       accept_new_options=True, placeholder="Elige o escribe…")
            regions = c2.multiselect("Regiones, ríos y rutas", with_extra(SC_REGIONS, sc0.regions), sc0.regions,
                                     accept_new_options=True, placeholder="Elige o escribe…")
            cities = c3.multiselect("Ciudades y puertos", with_extra(SC_CITIES, sc0.cities), sc0.cities,
                                    accept_new_options=True, placeholder="Elige o escribe…")
            c1, c2 = st.columns(2)
            categories = c1.multiselect("Solo estas categorías (vacío = todas)", list(scenario.CATEGORIES),
                                        sc0.categories, placeholder="Elige…")
            materials = c2.multiselect("Solo estos materiales (vacío = todos)", list(MATERIAL_ALIASES),
                                       sc0.materials, placeholder="Elige…")
            if st.form_submit_button("Calcular impacto", type="primary"):
                st.session_state["sc_calc"] = scenario.Scenario(
                    title=title, event_type=event, countries=countries, regions=regions, cities=cities,
                    categories=categories, materials=materials, duration_value=dur or None,
                    duration_unit="days" if dur else None).model_dump()

    calc = st.session_state.get("sc_calc")
    if calc:
        imp = scenario.simulate(scenario.Scenario.model_validate(calc))
        sc = imp.scenario
        st.markdown(f"##### {html.escape(sc.title)}")
        dur_txt = (f"{sc.duration_days} días (del escenario)" if sc.duration_days is not None else
                   "sin indicar: TTR por defecto del tipo de evento (estimado)")
        st.caption(f"{EVENT_LABELS_ES.get(sc.event_type, sc.event_type)} · duración {dur_txt} · lugares: "
                   f"{', '.join(sc.places) or 'todos'} · categorías: {', '.join(sc.categories) or 'todas'} · "
                   f"materiales: {', '.join(sc.materials) or 'todos'}")
        if imp.note:
            st.warning(imp.note)
        if imp.unmatched_places:
            st.warning("Sin proveedores de Helixa (o nombre no reconocido): " + ", ".join(imp.unmatched_places))
        if imp.excluded:
            st.caption("En la zona pero fuera del escenario (categoría, material o servicio no afectado por "
                       "transporte): " + ", ".join(f"{i} {SUP[i].name}" for i in imp.excluded))
        if not imp.hits:
            st.info("Ningún proveedor de Helixa queda afectado por este escenario.")
        else:
            mats, prods = imp.materials_table(), imp.products_table()
            worst_m = min(c.margin_days for c in imp.countdowns)
            stats = [(str(len(imp.hits)), "proveedores afectados"), (str(len(mats)), "materiales"),
                     (str(len(prods)), "productos"),
                     (f"{imp.spend_exposed / 1e6:.1f} M€".replace(".", ","), "gasto anual expuesto"),
                     (f"{imp.spend_at_risk / 1e6:.1f} M€".replace(".", ","), "gasto con déficit previsto"),
                     (f"{worst_m:+.0f} d", "peor margen")]
            for col, (n, lab) in zip(st.columns(len(stats)), stats):
                col.markdown(f'<div class="stat"><div class="n">{n}</div><div class="l">{lab}</div></div>',
                             unsafe_allow_html=True)
            st.write("")
            cd_by = {c.supplier_id: c for c in imp.countdowns}
            sim_exposure = {h.supplier.id: {"margin": cd_by[h.supplier.id].margin_days,
                                            "status": cd_by[h.supplier.id].status,
                                            "hover": "Motivo: " + "; ".join(h.reasons)} for h in imp.hits}
            show_map(exposure_map(sim_exposure, "Fuera del escenario"))

            st.markdown("**Proveedores afectados** (margen = TTS − TTR)")
            st.dataframe(pd.DataFrame([{
                "ID": h.supplier.id, "Proveedor": h.supplier.name, "Ciudad": h.supplier.city,
                "Categoría": h.supplier.category, "Motivo": "; ".join(h.reasons),
                "TTS (d)": c.tts_days if c.inventory_days is not None else None,
                "TTR (d)": c.ttr_days, "TTR": "estimado" if c.ttr_estimated else "del escenario",
                "Margen (d)": c.margin_days if c.inventory_days is not None else None,
                "Déficit (d)": c.deficit_days, "Estado": STATUS[c.status][0],
                "Gasto anual (€)": h.supplier.annual_spend_eur or 0}
                for h in imp.hits for c in [cd_by[h.supplier.id]]]).sort_values("Déficit (d)", ascending=False),
                hide_index=True, width="stretch",
                column_config={"Gasto anual (€)": st.column_config.NumberColumn(format="%.0f"),
                               "Margen (d)": st.column_config.NumberColumn(format="%+.0f")})
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Materiales**")
                st.dataframe(pd.DataFrame([{
                    "Material": m["material"],
                    "Principal": m["primary"] + (" ⚠" if m["primary_hit"] else ""),
                    "Alternativo": (m["alternate"] + (" ⚠" if m["alternate_hit"] else "")) or "—",
                    "Peor margen (d)": m["margin"], "Estado": STATUS[m["status"]][0],
                    "Necesidad mensual": m["monthly"]} for m in mats]),
                    hide_index=True, width="stretch",
                    column_config={"Peor margen (d)": st.column_config.NumberColumn(format="%+.0f")})
                st.caption("⚠ = afectado por el escenario. Un material sin fila no depende de ningún "
                           "proveedor afectado.")
            with c2:
                st.markdown("**Productos**")
                st.dataframe(pd.DataFrame([{
                    "Producto": p["product"], "Materiales afectados": ", ".join(p["materials"]),
                    "Peor margen (d)": p["margin"], "Estado": STATUS[p["status"]][0]} for p in prods]),
                    hide_index=True, width="stretch",
                    column_config={"Peor margen (d)": st.column_config.NumberColumn(format="%+.0f")})
            st.markdown("**Acciones recomendadas** (del menor margen al mayor)")
            for sid, text in imp.actions():
                st.markdown(f"- {html.escape(text)}")
            st.caption("Logística y servicios no tienen inventario: el impacto es inmediato durante toda la "
                       "duración y cuenta como déficit, aunque exista un alternativo. Supuestos de la cuenta "
                       "atrás: docs/fase3_cuenta_atras.md.")


# ---------------------------------------------------------------------------
# Transparencia
# ---------------------------------------------------------------------------
CHANGES = [  # versión, cambio, de dónde sale, efecto en las respuestas
    ("v2", "Gravedad = media de LLM y reglas (redondeo hacia arriba); el prompt explicita que adquisición, "
           "cambio de CEO o rebaja de rating son riesgo; una noticia positiva conserva el ID nombrado",
     "Entrenamiento", "Sí"),
    ("v3", "El LLM pasa por la misma comprobación de identidad que las reglas: un nombre ambiguo necesita "
           "contexto que lo respalde (N034 «Atlas Air»)", "Validación ⚠", "Sí"),
    ("v4", "Una restricción o veto a la exportación es siempre urgente, aunque sea temporal (N041; ejemplo "
           "explícito del README)", "Validación ⚠ + README", "Sí"),
    ("v5", "Política de desempate entre reglas y LLM: manda el LLM en los tres campos (4 discrepancias en 40 "
           "noticias, sin diferencia clara)", "Entrenamiento + validación", "No"),
    ("v6", "Definición del campo confidence: el LLM mezclaba escalas (80 o 4) y el validador convertía 4 en 0,04",
     "Fallo detectado al revisar discrepancias del test", "No"),
    ("v7", "Revisión humana si la confianza es baja o si reglas y LLM no coinciden",
     "Entrenamiento + validación", "No"),
    ("v8", "Duración de la recuperación en las unidades de la noticia (48 horas ≠ 48 días) y anclada al texto",
     "Robustez detectada en el test", "No"),
    ("v9", "La acción recomendada sale de la cuenta atrás: si el alternativo no llega a tiempo o también está "
           "afectado, no se propone como solución; se indican los días de déficit y otras medidas",
     "Incoherencia detectada en el test (N004)", "No"),
]
LIMITS = [
    ("N044 · racionamiento eléctrico en Zhejiang", "Sale urgente (gravedad 3 + proveedor único S003) y la etiqueta "
     "dice que no. Los dos jueces se equivocan igual, así que la revisión no salta. Falsa alarma, el error menos "
     "costoso según la prioridad del reto."),
    ("Riesgo por mera ubicación", "El LLM tiende a marcar como riesgo noticias que solo coinciden por ubicación "
     "(en el test: N021, N036, N049). Mitigación: no hay consenso con las reglas -> decisión humana requerida, y la "
     "respuesta de los compradores."),
    ("N037 · bajo nivel del Rin (entrenamiento)", "El LLM no lo ve como riesgo; las reglas sí. Sin consenso -> "
     "va a revisión."),
    ("Confianza del LLM", "Es casi constante (0,95) y no separa aciertos de errores: por eso la incertidumbre se mide "
     "con el consenso entre reglas y LLM."),
    ("Valores por defecto del TTR", "Órdenes de magnitud generales, marcados como estimados; el cliente los "
     "sustituye por su histórico."),
    ("Pocos datos", "30 noticias de entrenamiento y 10 de validación: cada noticia de validación vale 10 puntos."),
]


def consensus_stats(rs: list[dict]) -> dict:
    rows = [r for r in rs if r.get("gold") and r.get("consensus") is not None]
    if not rows:
        return {}
    agree = [r for r in rows if r["consensus"]]
    disagree = [r for r in rows if not r["consensus"]]
    wrong = [r for r in rows if not results.is_perfect(r)]
    return {"Consenso reglas-LLM": len(agree) / len(rows),
            "Perfecta con consenso": sum(map(results.is_perfect, agree)) / len(agree) if agree else float("nan"),
            "Perfecta sin consenso": (sum(map(results.is_perfect, disagree)) / len(disagree)
                                      if disagree else float("nan")),
            "Marcadas para revisión": sum(bool(r.get("needs_review")) for r in rows) / len(rows),
            "Errores que van a revisión": (sum(bool(r.get("needs_review")) for r in wrong) / len(wrong)
                                           if wrong else float("nan"))}


def history_table() -> str:
    """Tabla de historial de métricas de docs/evaluacion.md (la primera tabla del documento)."""
    text = (ROOT / "docs" / "evaluacion.md").read_text(encoding="utf-8")
    m = re.search(r"((?:^\|.*\|\s*$\n?)+)", text, flags=re.M)
    return m.group(1) if m else ""


with tab_transp:
    st.markdown("#### Cómo de bien funciona (y cómo lo sabemos)")
    st.caption("Las reglas, el diccionario geográfico y los prompts se diseñan solo con el entrenamiento y el README; "
               "la validación solo se mide. El entrenamiento con LLM se evalúa leave-one-out; las reglas se "
               "diseñaron con esas noticias, así que su cifra de entrenamiento es optimista.")
    table, cons = {}, {}
    for sp in ("train", "validation"):
        d = get(sp)
        if not d:
            continue
        name = results.SPLITS[sp]
        table[f"{name} · reglas"] = results.metrics(d["results"], "reglas")
        table[f"{name} · LLM (entrega)"] = results.metrics(d["results"])
        cons[name] = consensus_stats(d["results"])
    if table:
        t = pd.DataFrame(table)
        st.dataframe(t.apply(lambda col: [f"{int(v)}" if i == "Noticias" else pct(v) for i, v in col.items()]),
                     width="stretch")
        st.markdown("**Consenso entre reglas y LLM como señal de incertidumbre**")
        st.dataframe(pd.DataFrame(cons).apply(lambda col: col.map(pct)), width="stretch")
        st.caption("La confianza que declara el LLM es casi constante y no distingue aciertos de errores; "
                   "la discrepancia entre los dos jueces sí. Por eso activa la «decisión humana requerida».")

    st.markdown("#### Cambios y de dónde salen")
    st.dataframe(pd.DataFrame(CHANGES, columns=["Versión", "Cambio", "Motivado por", "¿Cambia respuestas Y/N?"]),
                 hide_index=True, width="stretch")
    st.caption("⚠ = cambio motivado por un error de validación: la cifra de validación posterior ya no es una medida "
               "totalmente independiente. Los cambios detectados en el test no tocan ninguna respuesta Y/N.")

    st.markdown("#### Límites conocidos")
    for title, text in LIMITS:
        st.markdown(f"- **{title}.** {text}")

    st.markdown("#### Duraciones ancladas al texto")
    st.caption("El LLM devuelve la duración de la recuperación tal como aparece en la noticia (valor + unidad) y el "
               "código la pasa a días. Si no está escrita en la noticia, se descarta y la cuenta atrás usa un valor "
               "por defecto marcado como estimado.")
    dur = []
    for sp in results.SPLITS:
        d = get(sp)
        for r in (d["results"] if d else []):
            said = r.get("signals", {}).get("recovery_llm")
            if said:
                anchored = r["signals"].get("recovery_anchored", False)
                cd = (r.get("countdown") or [None])[0]
                used = "— (sin riesgo)" if cd is None else (
                    f"{cd['ttr_days']}" + (" (estimado)" if cd["ttr_estimated"] else " (de la noticia)"))
                dur.append({"Conjunto": results.SPLITS[sp], "Noticia": r["news_id"], "Titular": r["headline"],
                            "El LLM dijo": said, "¿Escrita en la noticia?": "Sí" if anchored else "No, descartada",
                            "TTR usado (d)": used})
    if dur:
        dd = pd.DataFrame(dur)
        kept = (dd["¿Escrita en la noticia?"] == "Sí").sum()
        st.markdown(f"**{kept} de {len(dd)}** duraciones propuestas por el LLM están escritas en la noticia; "
                    f"las otras {len(dd) - kept} eran suposiciones del modelo y se han descartado.")
        st.dataframe(dd, hide_index=True, width="stretch")

    with st.expander("Historial de métricas por versión (docs/evaluacion.md)"):
        st.markdown(history_table())
    with st.expander("Documento completo de evaluación"):
        st.markdown((ROOT / "docs" / "evaluacion.md").read_text(encoding="utf-8"))
