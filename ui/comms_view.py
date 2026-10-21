"""Pestaña «✉ Comunicar» de la ventana de la alerta: el agente de comunicaciones (core/comms.py).

«Preparar comunicaciones» redacta dos borradores editables (correo al proveedor en inglés, nota interna en
español) con la IA local y comprueba sus cifras; sin IA, plantilla. «Copiar» los copia al portapapeles y
«Marcar como enviado» lo registra en la auditoría (la tarjeta muestra «✉ Comunicado»). No se envía nada.
"""
from __future__ import annotations

import streamlit as st

from core import comms, tasks
from core.actions import plan_steps, situation
from core.labels import material_es, product_es

from . import cache
from .components import esc, md
from .data import Alert, meur, when

LEVEL_ES = {"critica": "crítica", "vigilar": "en vigilancia (riesgo latente)", "seguimiento": "en seguimiento semanal"}

# Botón «Copiar»: st.components.v2 (sin iframe) con la API del portapapeles; localhost es contexto seguro.
_COPY_JS = """
export default function (component) {
  const { data, parentElement } = component;
  const b = parentElement.querySelector('button');
  if (!b) return;
  b.onclick = async () => {
    const t = (data && data.text) || '';
    try { await navigator.clipboard.writeText(t); }
    catch (e) {
      const ta = document.createElement('textarea'); ta.value = t; document.body.appendChild(ta);
      ta.select(); document.execCommand('copy'); ta.remove();
    }
    b.textContent = 'Copiado ✓';
    setTimeout(() => { b.textContent = 'Copiar'; }, 1800);
  };
}
"""
_COPY_CSS = """
button.cp { width: 100%; min-height: 44px; border-radius: 8px; border: 1px solid #D5D1DD; background: #FFFFFF;
  font: 600 15px 'IBM Plex Sans', system-ui, sans-serif; color: #17151C; cursor: pointer; }
button.cp:hover { border-color: #A100FF; background: #FBF7FF; }
button.cp:focus-visible { outline: 2px solid #A100FF; outline-offset: 2px; }
"""
_copy = st.components.v2.component("copy_text", html='<button class="cp" type="button">Copiar</button>',
                                   css=_COPY_CSS, js=_COPY_JS)


def facts(a: Alert) -> comms.Facts:
    """Los datos de la alerta que pueden aparecer en los borradores (y nada más)."""
    s, c = a.supplier, a.worst
    steps = plan_steps(c, s, urgent=a.level == "critica")
    if s.single_source or not s.alternate_id:
        dep = "proveedor único"
    else:
        dep = f"alternativo aprobado: {s.alternate_name or s.alternate_id}"
    return comms.Facts(
        supplier=s.name, material_en=s.material, material_es=material_es(s.material),
        products_en=list(a.products), products_es=[product_es(p) for p in a.products],
        event_en=a.r.get("event_label", a.r["event_type"]), headline=a.r["headline"],
        source=a.r.get("source") or "news", date=str(a.r.get("published_date") or "")[:10],
        level_es=LEVEL_ES[a.level], what_es=a.what(), inventory_days=c.inventory_days, recovery_days=c.ttr_days,
        recovery_estimated=c.ttr_estimated, margin_days=c.margin_days, spend_meur=meur(s.annual_spend_eur or 0),
        dependency_es=dep, steps=steps,
        ask_partial=situation(c, s) in ("unico_deficit", "alt_afectado")
        or any("asignación parcial" in x.text for x in steps))


def _prepare(k: str, a: Alert) -> None:
    f = facts(a)
    with st.spinner("La IA local está redactando los borradores…" if cache.llm_up() else "Preparando la plantilla…"):
        p = comms.prepare(f, use_llm=cache.llm_up())
    st.session_state[f"cm-sub-{k}"] = p.drafts.email_subject
    st.session_state[f"cm-mail-{k}"] = p.drafts.email_body
    st.session_state[f"cm-note-{k}"] = p.drafts.note
    st.session_state[f"cm-info-{k}"] = {"source": p.source, "reason": p.reason, "seconds": round(p.seconds, 1),
                                        "attempts": p.attempts}


def _send(split: str, a: Alert, k: str, kind: str, info: dict) -> None:
    if kind == "correo":
        recipient, subject, body = a.supplier.name, st.session_state[f"cm-sub-{k}"], st.session_state[f"cm-mail-{k}"]
    else:
        recipient, subject, body = "Equipo de compras", "Nota interna", st.session_state[f"cm-note-{k}"]
    tasks.log_communication(split, a.id, kind, recipient, subject, body, info["source"],
                            user="director de compras (panel)", con=cache.db())
    st.session_state["toast"] = (f"{tasks.COMM_KINDS[kind]} marcado como enviado · registrado en la auditoría "
                                 "(no se ha enviado nada)", "✉️")
    st.rerun()


def panel(split: str, a: Alert, sent: list[dict]) -> None:
    k = f"{split}-{a.id}"
    if st.button("Preparar comunicaciones", key=f"cmgo-{k}", type="primary", width="stretch",
                 help="Correo al proveedor (inglés) y nota interna (español), con los datos de la alerta"):
        _prepare(k, a)
    info = st.session_state.get(f"cm-info-{k}")
    if not info:
        md('<p class="sub">Redacta un correo al proveedor y una nota para el equipo con los datos de esta alerta. '
           'Son borradores editables: no se envía nada.</p>')
        return
    if info["source"] == "ia":
        took = ("al instante (respuesta en caché)" if info["seconds"] < 0.5 else
                f"en {str(info['seconds']).replace('.', ',')} s")
        md(f'<p class="calc cm-info">✓ Redactado por la IA local {took}. Todas las cifras coinciden con las de la '
           'alerta (comprobado por código).</p>')
    else:
        md(f'<p class="calc cm-info">Plantilla: {esc(info["reason"])}.</p>')
    f = facts(a)
    for kind, label in (("correo", "Correo al proveedor · inglés"), ("nota", "Nota interna · español")):
        md(f'<h3 class="h3">{label}</h3>')
        if kind == "correo":
            st.text_input("Asunto", key=f"cm-sub-{k}")
            text = st.text_area("Correo", key=f"cm-mail-{k}", height=230, label_visibility="collapsed")
            full = st.session_state[f"cm-sub-{k}"] + "\n" + text
        else:
            text = st.text_area("Nota", key=f"cm-note-{k}", height=260, label_visibility="collapsed")
            full = text
        extra = comms.extra(full, f)
        if extra:            # el comprador ha editado y ha escrito una cifra que no está en la alerta
            st.warning("Cifras que no están en la alerta: " + ", ".join(extra))
        done = [x for x in sent if x["channel"] == kind]
        c1, c2 = st.columns(2)
        with c1:
            _copy(data={"text": full if kind == "correo" else text}, key=f"cmcp-{kind}-{k}")
        if c2.button("Marcar como enviado", key=f"cmsent-{kind}-{k}", width="stretch",
                     help="Lo registra en la auditoría; no se envía nada"):
            _send(split, a, k, kind, info)
        if done:
            md(f'<p class="sub">✉ Marcado como enviado el {esc(when(done[-1]["ts"]))}.</p>')
