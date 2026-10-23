"""Pestaña «✉ Comunicar» de la ventana de la alerta: el agente de comunicaciones (core/comms.py).

«Preparar comunicaciones» redacta dos borradores editables (correo al proveedor en inglés, nota interna en
español) con la IA local y comprueba sus cifras; sin IA, plantilla. «Copiar» los copia al portapapeles y
«Enviar» manda el borrador por correo (core/mailer.py) tras una confirmación que muestra destinatario y asunto
y comprueba las cifras; «Marcar como enviado» solo lo registra (la tarjeta muestra «✉ Comunicado»). Nada sale
sin pulsar «Enviar» y confirmar.
"""
from __future__ import annotations

import streamlit as st

from core import comms, mailer, tasks
from core.actions import plan_steps, situation
from core.labels import material_es, product_es

from . import cache
from .components import esc, md
from .data import Alert, meur, when

BUYER = "Director de compras"        # el comprador que firma las notas internas (asunto del correo)
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


def _mark(split: str, a: Alert, k: str, kind: str, info: dict) -> None:
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
           'Son borradores editables: nada se envía sin tu confirmación.</p>')
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
        c1, c2, c3 = st.columns(3)
        with c1:
            _copy(data={"text": full if kind == "correo" else text}, key=f"cmcp-{kind}-{k}")
        c2.button("Enviar", key=f"cmsend-{kind}-{k}", type="primary", width="stretch", on_click=_ask, args=(k, kind),
                  help="Pide confirmación antes de enviar: nada sale sin que la confirmes")
        if c3.button("Marcar enviado", key=f"cmsent-{kind}-{k}", width="stretch",
                     help="Lo registra en la auditoría sin enviar nada (si lo has enviado por tu cuenta)"):
            _mark(split, a, k, kind, info)
        if st.session_state.get(f"cm-ask-{k}") == kind:
            _confirm(split, a, k, kind, info, f, st.session_state[f"cm-sub-{k}"] if kind == "correo" else "", text)
        _history(k, kind, done)


def _history(k: str, kind: str, done: list[dict]) -> None:
    """Lo ya hecho con este borrador: envíos reales, simulados (con su motivo y el .eml) y marcas manuales."""
    for x in done[-3:]:
        hm = esc(x["ts"][11:16])
        if x.get("delivery") == "real":
            md(f'<p class="sub">✉ Enviado {hm} a {esc(x["to_addr"])} · registrado en la auditoría.</p>')
        elif x.get("delivery") == "simulado":
            md(f'<p class="sub">✉ Simulado {hm} · {esc(x["error"])}</p>')
        else:
            md(f'<p class="sub">✉ Marcado como enviado el {esc(when(x["ts"]))}.</p>')
    last = st.session_state.get(f"cm-res-{k}-{kind}")
    if last and last["delivery"] == "simulado":
        st.download_button("Descargar el .eml", data=last["eml"], file_name=f"{kind}-{k}.eml",
                           mime="message/rfc822", key=f"cmeml-{kind}-{k}")


def _ask(k: str, kind: str) -> None:
    st.session_state[f"cm-ask-{k}"] = kind


def _cancel(k: str) -> None:
    st.session_state.pop(f"cm-ask-{k}", None)


def _confirm(split: str, a: Alert, k: str, kind: str, info: dict, f: comms.Facts, subject: str, body: str) -> None:
    """Confirmación humana: destinatario y asunto, y la comprobación previa. Nada se envía sin pulsar el botón."""
    cfg = mailer.config()
    p = mailer.plan(kind, a.supplier.name, subject, body, BUYER, a.id, cfg, demo=cache.demo_on())
    problems = comms.send_issues(kind, subject, body, f)
    with st.container(key=f"cmconf-{kind}-{k}"):
        md('<h3 class="h3">Confirmar envío</h3>'
           f'<div class="srow"><span class="l">Para</span><span class="v">{esc(p.to_line)}</span></div>'
           f'<div class="srow"><span class="l">Asunto</span><span class="v">{esc(p.subject)}</span></div>')
        if problems:
            st.error("No se envía. " + " ".join(problems) + " Corrige el borrador.")
            st.button("Cerrar", key=f"cmno-{kind}-{k}", on_click=_cancel, args=(k,))
            return
        miss = cfg.missing()
        aviso = (f"Sin configuración SMTP (falta {', '.join(miss)} en .env): quedará como simulado." if miss
                 else f"Se enviará de verdad a {p.to_addr}.")
        md(f'<p class="sub">{esc(aviso)}</p>')
        b1, b2 = st.columns(2)
        if b1.button("Confirmar y enviar", key=f"cmyes-{kind}-{k}", type="primary", width="stretch"):
            with st.spinner("Enviando…"):
                res = mailer.send(p, cfg)
            tasks.log_communication(split, a.id, kind, p.display_to, p.subject, p.body, info["source"],
                                    user="director de compras (panel)", con=cache.db(), delivery=res.delivery,
                                    to_addr=p.to_addr if res.delivery == "real" else "", error=res.reason)
            st.session_state[f"cm-res-{k}-{kind}"] = {"delivery": res.delivery, "eml": res.eml}
            st.session_state.pop(f"cm-ask-{k}", None)
            st.session_state["toast"] = (("Correo enviado" if res.delivery == "real" else "Envío simulado")
                                         + " · registrado en la auditoría", "✉️")
            st.rerun()
        b2.button("Cancelar", key=f"cmno-{kind}-{k}", width="stretch", on_click=_cancel, args=(k,))
