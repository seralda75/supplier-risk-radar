"""Compradores, suscripciones y avisos de Telegram en SQLite (core/subscriptions.py)."""
from core import demo, feedback, subscriptions as subs
from core.recurrence import load_history

REF = max(o.day for o in load_history())         # día de referencia del historial sintético


def test_registrar_suscribe_a_los_proveedores_habituales(tmp_path):
    con = feedback.connect(tmp_path / "a.db")
    subs.register(111, "B2", "Móvil de Pablo", REF, con)
    b = subs.buyer(111, con)
    assert b["name"] == "Pablo Navarro" and "Primary packaging" in b["categories"]
    auto = {f["supplier_id"] for f in subs.followed(111, con) if f["origin"] == "auto"}
    assert {"S015", "S017", "S020", "S022"} <= auto
    assert "S003" not in auto and "S019" not in auto      # otro comprador; alternativo con un pedido puntual
    assert 111 in subs.subscribers("S015", REF, con)
    # varios chats a la vez, también como el mismo comprador
    subs.register(222, "B2", "", REF, con)
    subs.register(333, "B1", "", REF, con)
    assert subs.subscribers("S015", REF, con) == [111, 222]
    assert subs.subscribers("S003", REF, con) == [333]


def test_seguir_y_dejar(tmp_path):
    con = feedback.connect(tmp_path / "a.db")
    subs.register(111, "B2", "", REF, con)
    subs.follow(111, "S019", con)                         # manual
    assert {"supplier_id": "S019", "origin": "manual"} in subs.followed(111, con)
    assert subs.unfollow(111, "S015", con)                # también una automática
    assert not subs.unfollow(111, "S015", con)            # ya no la seguía
    assert 111 not in subs.subscribers("S015", REF, con)  # la sincronización no la vuelve a crear
    subs.follow(111, "S015", con)
    assert 111 in subs.subscribers("S015", REF, con)


def test_cambiar_de_comprador_quita_las_automaticas_y_conserva_las_manuales(tmp_path):
    con = feedback.connect(tmp_path / "a.db")
    subs.register(111, "B2", "", REF, con)
    subs.follow(111, "S030", con)
    subs.register(111, "B1", "", REF, con)
    ids = {f["supplier_id"] for f in subs.followed(111, con)}
    assert "S015" not in ids and "S003" in ids and "S030" in ids


def test_un_aviso_por_chat_y_alerta(tmp_path):
    con = feedback.connect(tmp_path / "a.db")
    n = subs.claim(111, "test", "N024", "urgente", ["S025"], "línea", con)
    assert n is not None
    assert subs.claim(111, "test", "N024", "urgente", ["S025"], "línea", con) is None
    subs.mark(n, "enviado", 99, con=con)
    assert subs.sent("N024", con)[0]["status"] == "enviado"
    r = subs.claim(111, "test", "N030", "resumen", ["S011"], "Iberia: dificultades financieras", con)
    assert [p["news_id"] for p in subs.pending_summary(111, con=con)] == ["N030"]
    subs.mark(r, "resumido", con=con)
    assert subs.pending_summary(111, con=con) == []


def test_reiniciar_demo_borra_avisos_y_suscripciones_pero_no_los_chats(tmp_path):
    con = demo.connect(tmp_path / "demo.db")
    subs.register(111, "B1", "", REF, con)
    subs.follow(111, "S040", con)
    subs.claim(111, "test", "N008", "urgente", ["S012"], "", con)
    demo.reset(con)
    assert subs.buyer(111, con)["buyer_id"] == "B1"
    assert subs.sent(con=con) == []
    assert "S040" not in {f["supplier_id"] for f in subs.followed(111, con)}
    assert 111 in subs.subscribers("S012", REF, con)       # las automáticas se recrean solas
