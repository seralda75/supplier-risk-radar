"""Envío real de las comunicaciones por correo (smtplib + STARTTLS), siempre con confirmación humana.

Los proveedores de Helixa son ficticios y los datos del reto no traen su correo: todo lo que sale del panel
llega a DEMO_RECIPIENT (la bandeja de la demo), también en modo no demo mientras el proveedor no tenga correo.
Sin configuración SMTP, o si el envío falla (red bloqueada, credenciales), no se rompe nada: el envío queda
«simulado», con el motivo, y se puede descargar el .eml.

La configuración sale de .env (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, DEMO_RECIPIENT). La contraseña
solo se usa en login(): no se imprime, no se registra y se quita de cualquier mensaje de error.
"""
from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from dotenv import dotenv_values

from .config import ROOT

TIMEOUT_S = 15


@dataclass
class Config:
    host: str = ""
    port: int = 587
    user: str = ""
    password: str = ""
    recipient: str = ""

    def missing(self) -> list[str]:
        """Variables de .env que faltan para poder enviar de verdad."""
        need = {"SMTP_HOST": self.host, "SMTP_USER": self.user, "SMTP_PASSWORD": self.password,
                "DEMO_RECIPIENT": self.recipient}
        return [k for k, v in need.items() if not v]


def config() -> Config:
    """Configuración actual: .env tiene prioridad sobre el entorno y se relee en cada envío (se puede rellenar
    con la app abierta)."""
    env = {**os.environ, **{k: v for k, v in dotenv_values(ROOT / ".env").items() if v}}
    try:
        port = int(env.get("SMTP_PORT") or 587)
    except ValueError:
        port = 587
    g = lambda k: (env.get(k) or "").strip()      # noqa: E731
    return Config(g("SMTP_HOST"), port, g("SMTP_USER"), env.get("SMTP_PASSWORD") or "", g("DEMO_RECIPIENT"))


@dataclass
class Plan:
    """Lo que se va a enviar y a quién llegará de verdad (se enseña en la confirmación)."""
    kind: str                      # correo | nota
    display_to: str                # «Para:» (el proveedor, o «Equipo de compras»)
    to_addr: str                   # destinatario real
    subject: str
    body: str
    redirected: bool               # el proveedor no tiene correo (o modo demo): va a la bandeja de la demo

    @property
    def to_line(self) -> str:
        if self.redirected:
            return f"{self.display_to} (redirigido a la bandeja de la demo)"
        return self.display_to


def plan(kind: str, supplier: str, subject: str, body: str, buyer: str, news_id: str, cfg: Config,
         demo: bool = False, supplier_email: str | None = None) -> Plan:
    """Destinatario y asunto finales. Correo al proveedor: a su correo, salvo en modo demo o si no lo tiene (va a
    DEMO_RECIPIENT). Nota interna: siempre a DEMO_RECIPIENT, con el nombre del comprador en el asunto."""
    if kind == "nota":
        return Plan(kind, "Equipo de compras", cfg.recipient, f"Nota interna · {buyer} · {supplier} ({news_id})",
                    body, False)
    redirected = demo or not supplier_email
    return Plan(kind, supplier, cfg.recipient if redirected else str(supplier_email), subject, body, redirected)


def message(p: Plan, sender: str) -> EmailMessage:
    """El correo con sus cabeceras. Si va redirigido, se indica el destinatario original al pie."""
    m = EmailMessage()
    m["From"] = sender or "helixa-procurement@localhost"
    m["To"] = p.to_addr or "demo@localhost"
    m["Subject"] = p.subject
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain="helixa.local")
    body = p.body
    if p.redirected and p.kind == "correo":
        body += f"\n\n[Demo: destinatario original, {p.display_to} (proveedor ficticio)]"
        m["X-Helixa-Original-To"] = p.display_to
    m.set_content(body)
    return m


@dataclass
class Result:
    delivery: str                  # real | simulado
    reason: str                    # por qué fue simulado (vacío si fue real)
    eml: bytes


def _scrub(text: str, cfg: Config) -> str:
    return text.replace(cfg.password, "***") if cfg.password else text


def send(p: Plan, cfg: Config | None = None) -> Result:
    """Envía por SMTP con STARTTLS. Nunca lanza: sin configuración o con un fallo, devuelve «simulado»."""
    cfg = cfg or config()
    msg = message(p, cfg.user)
    eml = bytes(msg)
    miss = cfg.missing()
    if miss:
        return Result("simulado", "falta configurar en .env: " + ", ".join(miss), eml)
    try:
        with smtplib.SMTP(cfg.host, cfg.port, timeout=TIMEOUT_S) as s:
            s.ehlo()
            s.starttls(context=ssl.create_default_context())
            s.ehlo()
            s.login(cfg.user, cfg.password)
            s.send_message(msg)
    except Exception as e:                      # red bloqueada, credenciales, tiempo de espera...
        detail = _scrub(str(e), cfg).strip().replace("\n", " ")[:90]
        return Result("simulado", f"no se pudo enviar ({type(e).__name__}{': ' + detail if detail else ''})", eml)
    return Result("real", "", eml)
