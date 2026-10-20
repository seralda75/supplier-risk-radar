"""Transparencia: cómo de bien funciona el sistema y cómo lo sabemos (la parte técnica del panel).

Métricas de entrenamiento y validación (reglas frente a IA), consenso como señal de incertidumbre,
cambios y de dónde salen, límites conocidos y duraciones ancladas al texto.
"""
from __future__ import annotations

import math
import re

import streamlit as st

from core import results

from . import cache
from .components import esc, md, table

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


def _pct(v) -> str:
    return "—" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.1%}".replace(".", ",")


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
    text = cache.doc("evaluacion.md")
    m = re.search(r"((?:^\|.*\|\s*$\n?)+)", text, flags=re.M)
    return m.group(1) if m else ""


def _section(title: str, body: str, note: str = "") -> None:
    n = f'<span class="sub">{note}</span>' if note else ""
    md(f'<section class="card"><div class="card-head"><h2 class="h2">{esc(title)}</h2>{n}</div>{body}</section>')


def render() -> None:
    loaded = cache.all_data()
    md('<div style="display:flex;flex-direction:column;gap:4px"><span class="overline">Cómo de bien funciona y '
       'cómo lo sabemos</span><h1 class="h1">Transparencia</h1></div>')

    cols, cons = {}, {}
    for sp in ("train", "validation"):
        d = loaded.get(sp)
        if not d:
            continue
        name = results.SPLITS[sp]
        cols[f"{name} · reglas"] = results.metrics(d["results"], "reglas")
        cols[f"{name} · LLM (entrega)"] = results.metrics(d["results"])
        cons[name] = consensus_stats(d["results"])
    if cols:
        names = list(next(iter(cols.values())))
        rows = [[esc(m)] + [(f'<span class="num">{int(c[m])}</span>' if m == "Noticias" else
                             f'<span class="num">{_pct(c[m])}</span>') for c in cols.values()] for m in names]
        _section("Métricas: reglas frente a IA",
                 table(["Métrica"] + list(cols), rows, right=set(range(1, len(cols) + 1)))
                 + '<span class="sub">Las reglas, el diccionario geográfico y los prompts se diseñan solo con el '
                   'entrenamiento y el README; la validación solo se mide. El entrenamiento con LLM se evalúa '
                   'leave-one-out; las reglas se diseñaron con esas noticias, así que su cifra es optimista.</span>')
        names = list(next(iter(cons.values())))
        rows = [[esc(m)] + [f'<span class="num">{_pct(c.get(m))}</span>' for c in cons.values()] for m in names]
        _section("Consenso entre reglas e IA como señal de incertidumbre",
                 table(["Señal"] + list(cons), rows, right=set(range(1, len(cons) + 1)))
                 + '<span class="sub">La confianza que declara la IA es casi constante y no distingue aciertos de '
                   'errores; la discrepancia entre los dos jueces sí. Por eso activa la revisión humana.</span>')

    rows = [[f'<span class="num">{v}</span>', esc(c), esc(o), esc(y)] for v, c, o, y in CHANGES]
    _section("Cambios y de dónde salen", table(["Versión", "Cambio", "Motivado por", "¿Cambia Y/N?"], rows)
             + '<span class="sub">⚠ = cambio motivado por un error de validación: la cifra de validación posterior ya '
               'no es una medida totalmente independiente. Los cambios detectados en el test no tocan ninguna '
               'respuesta Y/N.</span>')

    _section("Límites conocidos", '<ul style="margin:0;padding-left:18px;display:flex;flex-direction:column;gap:8px">'
             + "".join(f"<li><strong>{esc(t)}.</strong> {esc(x)}</li>" for t, x in LIMITS) + "</ul>")

    dur = []
    for sp in results.SPLITS:
        d = loaded.get(sp)
        for r in (d["results"] if d else []):
            said = r.get("signals", {}).get("recovery_llm")
            if not said:
                continue
            anchored = r["signals"].get("recovery_anchored", False)
            cd = (r.get("countdown") or [None])[0]
            used = "— (sin riesgo)" if cd is None else (
                f"{cd['ttr_days']} d" + (" (estimado)" if cd["ttr_estimated"] else " (de la noticia)"))
            dur.append([esc(results.SPLITS[sp]), f'<span class="num">{esc(r["news_id"])}</span>', esc(r["headline"]),
                        f'<span class="num">{esc(said)}</span>',
                        "Sí" if anchored else '<span style="color:#8C1D18">No, descartada</span>', esc(used)])
    if dur:
        kept = sum(1 for x in dur if x[4] == "Sí")
        _section("Duraciones ancladas al texto",
                 f'<p class="what" style="font-size:15px"><strong>{kept} de {len(dur)}</strong> duraciones propuestas '
                 f'por la IA están escritas en la noticia; las otras {len(dur) - kept} eran suposiciones del modelo y '
                 'se han descartado (la cuenta atrás usa entonces un valor por defecto marcado como estimado).</p>'
                 + table(["Conjunto", "Noticia", "Titular", "La IA dijo", "¿En la noticia?", "Plazo usado"], dur))

    with st.expander("Historial de métricas por versión (docs/evaluacion.md)"):
        st.markdown(history_table())
    with st.expander("Documento completo de evaluación"):
        st.markdown(cache.doc("evaluacion.md"))
