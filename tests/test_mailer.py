"""Envío de comunicaciones: destinatario, comprobación previa, SMTP con STARTTLS y envío simulado."""
import smtplib

from core import comms, mailer


def facts():
    return comms.Facts(supplier="Taizhou Hengyuan Pharma", material_en="Metformin", material_es="metformina",
                       products_en=["Glucora 850 mg tablets"], products_es=["Glucora 850 mg"], event_en="fire",
                       headline="Fire at Taizhou chemical park", source="Reuters", date="2026-10-18",
                       level_es="crítica", what_es="Incendio.", inventory_days=30, recovery_days=21,
                       recovery_estimated=False, margin_days=-9, spend_meur="2,6", dependency_es="proveedor único")


CFG = mailer.Config("smtp.example.com", 587, "u@example.com", "s3cret-pass", "demo@example.com")


def test_el_correo_al_proveedor_va_a_la_bandeja_de_la_demo():
    p = mailer.plan("correo", "Taizhou Hengyuan Pharma", "Supply status", "Dear team", "Ana", "N001", CFG)
    assert p.to_addr == "demo@example.com" and p.redirected
    assert p.to_line == "Taizhou Hengyuan Pharma (redirigido a la bandeja de la demo)"
    assert "Dear team" in mailer.message(p, CFG.user).get_content()


def test_la_nota_interna_lleva_al_comprador_en_el_asunto():
    p = mailer.plan("nota", "Taizhou Hengyuan Pharma", "", "Texto", "Ana", "N001", CFG)
    assert p.to_addr == "demo@example.com" and "Ana" in p.subject and not p.redirected


def test_sin_configuracion_queda_simulado_con_eml():
    p = mailer.plan("correo", "X", "S", "B", "Ana", "N001", mailer.Config())
    r = mailer.send(p, mailer.Config())
    assert r.delivery == "simulado" and "SMTP_USER" in r.reason and b"Subject: S" in r.eml


def test_envio_real_con_starttls_y_login(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None): calls.append(("conn", host, port))
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def starttls(self, context=None): calls.append("starttls")
        def login(self, u, pw): calls.append(("login", u))
        def send_message(self, m): calls.append(("send", m["To"]))
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    p = mailer.plan("nota", "X", "", "B", "Ana", "N001", CFG)
    r = mailer.send(p, CFG)
    assert r.delivery == "real" and calls == [("conn", "smtp.example.com", 587), "starttls", ("login", "u@example.com"),
                                              ("send", "demo@example.com")]


def test_un_fallo_de_red_no_rompe_y_no_muestra_la_contrasena(monkeypatch):
    def boom(*a, **k):
        raise OSError("connection refused for s3cret-pass")
    monkeypatch.setattr(smtplib, "SMTP", boom)
    r = mailer.send(mailer.plan("nota", "X", "", "B", "Ana", "N001", CFG), CFG)
    assert r.delivery == "simulado" and "OSError" in r.reason and "s3cret-pass" not in r.reason


def test_comprobacion_previa_cifras_y_datos_internos():
    f = facts()
    assert comms.send_issues("correo", "Supply", "Please confirm the status.", f) == []
    assert "Cifras que no están en la alerta" in comms.send_issues("correo", "Supply", "We need 999 units.", f)[0]
    fuga = comms.send_issues("correo", "Supply", "We hold 30 days of stock.", f)
    assert any("revela" in x for x in fuga)
    assert comms.send_issues("nota", "", "Quedan 30 días de stock.", f) == []     # la nota es interna


def test_la_tarjeta_muestra_enviado_simulado_o_comunicado():
    from ui.control import action_badges
    c = lambda **k: {"kind": "comm", "ts": "2026-10-23T14:32:10", **k}   # noqa: E731
    assert "✉ Enviado 14:32" in action_badges([c(delivery="real")])
    assert "✉ Simulado" in action_badges([c(delivery="simulado")])
    assert "✉ Comunicado" in action_badges([c(delivery="")])
