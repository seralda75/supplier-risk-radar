"""El panel arranca sin errores con los resultados guardados, en todas las páginas y conjuntos, sin llamar
al LLM, y todo lo que se puede pulsar hace algo (inventario de elementos clicables en docs/panel.md)."""
import re

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from datetime import date

from core import demo, feedback, results, scenario, tasks
from core.config import ROOT

APP = ROOT / "app.py"
PAGES = {"control": None, "calendar": "views/calendar.py", "suppliers": "views/suppliers.py",
         "simulator": "views/simulator.py", "transparency": "views/transparency.py",
         "settings": "views/settings.py"}
NAV = {"Centro de control": "", "Calendario": "calendario", "Proveedores": "proveedores",
       "Simulador «¿Y si…?»": "simulador", "Ajustes": "ajustes"}
NEEDS_RESULTS = pytest.mark.skipif(not results.path("test").exists(),
                                   reason="faltan data/results (scripts/build_results.py)")


@pytest.fixture(autouse=True)
def db_temporal(tmp_path, monkeypatch):
    # las decisiones de los botones van a una base de datos temporal, no a data/app.db ni a data/demo.db
    monkeypatch.setattr(feedback, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(demo, "DB_PATH", tmp_path / "demo.db")
    from ui import demo_view
    monkeypatch.setattr(demo_view, "STEP_S", 0)          # la demo sin pausas entre pasos
    monkeypatch.setattr(demo_view, "END_S", 0)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")         # nunca se envía nada de verdad desde los tests


@pytest.fixture(autouse=True)
def sin_llm(monkeypatch):
    from core import llm

    def prohibido(*a, **k):
        raise AssertionError("El panel no debe llamar al LLM")
    monkeypatch.setattr(llm, "extract", prohibido)
    monkeypatch.setattr(llm, "chat", prohibido)
    monkeypatch.setattr(llm, "is_up", lambda *a, **k: False)   # por defecto, como si Ollama estuviera apagado
    st.cache_data.clear()            # la comprobación de Ollama se cachea 30 s: cada test parte de cero
    st.cache_resource.clear()


def run(view="control"):
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.run()
    if PAGES[view]:
        at.switch_page(PAGES[view]).run()
    return at


def html(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def kpi_value(at, label: str) -> str:
    m = re.search(rf'<span class="k">{re.escape(label)}(?:<span class="tip".*?</span>)?</span>'
                  rf'<span class="v"><span class="\w+"[^>]*>([^<]+)<', html(at))
    assert m, label
    return m.group(1)


@NEEDS_RESULTS
@pytest.mark.parametrize("view", list(PAGES))
def test_cada_pagina_arranca(view):
    at = run(view)
    assert not at.exception, at.exception
    links = {(x.proto.label, x.proto.page) for x in at.get("page_link")}
    assert set(NAV.items()) <= links                      # el menú son enlaces reales a cada página
    assert "transparencia" not in {p for _, p in links}   # Transparencia: solo por URL directa


@NEEDS_RESULTS
def test_la_navegacion_cambia_de_pagina():
    at = run("suppliers")
    assert "Ranking de vulnerabilidad" in html(at) and "Requiere tu decisión" not in html(at)


@NEEDS_RESULTS
def test_simular_escenario_lleva_al_simulador():
    at = run()
    assert ("Simular escenario", "simulador") in {(x.proto.label, x.proto.page) for x in at.get("page_link")}


@NEEDS_RESULTS
def test_centro_de_control_en_lenguaje_de_negocio():
    page = html(run())
    for text in ("Requiere tu decisión", "Calendario de roturas", "¿Cuánto aguantamos?", "Dónde está el riesgo",
                 "¿Dónde está el gasto en riesgo?", "Plan recomendado", "Alertas críticas", "Gasto anual expuesto",
                 "del gasto total"):
        assert text in page
    # sin jerga: ni TTS/TTR ni IDs de proveedor en la vista de negocio
    assert "TTS" not in page and "TTR" not in page and "S025" not in page
    assert "Celsius Bioprocess Systems" in page and "días" in page


@NEEDS_RESULTS
def test_calendario_una_fila_por_medicamento_con_el_estado_en_texto():
    page = html(run())
    cal = page[page.index('class="cal"'):]
    assert cal.count('class="track"') == int(kpi_value(run(), "Medicamentos en riesgo"))
    assert "ROTURA" in cal and "Hoy" in cal and 'class="seg out' in cal
    assert 'class="seg out est"' in cal or 'class="seg back est"' in cal      # tramos estimados, con trama


@NEEDS_RESULTS
def test_la_cola_selecciona_la_alerta_y_abre_su_ventana():
    at = run()
    ids = [b.key.removeprefix("qbtn-") for b in at.button if b.key.startswith("qbtn-")]
    assert len(ids) >= 2
    at.button(key=f"qbtn-{ids[1]}").click().run()
    assert not at.exception, at.exception
    assert at.session_state["sel-test"] == ids[1]
    keys = {b.key for b in at.button}
    assert f"ok-test-{ids[1]}" in keys                  # el detalle muestra esa alerta
    assert f"dlg-ok-test-{ids[1]}" in keys              # y la ventana está abierta, con su decisión
    page = html(at)
    for text in ("Margen", "Calendario de", "Plan recomendado"):
        assert text in page


@NEEDS_RESULTS
def test_revisar_ahora_selecciona_la_mas_critica():
    at = run()
    first = at.session_state["sel-test"]                 # por defecto, la más crítica pendiente
    ids = [b.key.removeprefix("qbtn-") for b in at.button if b.key.startswith("qbtn-")]
    at.button(key=f"qbtn-{ids[2]}").click().run()
    at.button(key="review-now").click().run()
    assert at.session_state["sel-test"] == first == ids[0]


@NEEDS_RESULTS
def test_ver_noticia_original_muestra_la_noticia_completa():
    at = run()
    news = results.load("test")["results"]
    r = next(x for x in news if x["news_id"] == at.session_state["sel-test"])
    page = html(at)
    assert 'class="news-body"' in page and r["headline"] in page


@NEEDS_RESULTS
@pytest.mark.parametrize("prefix, verdict", [("fa", "falsa_alarma"), ("ok", "plan_aprobado")])
def test_las_decisiones_se_guardan_en_sqlite(prefix, verdict):
    at = run()
    boton = next(b for b in at.button if b.key.startswith(f"{prefix}-test-"))
    boton.click().run()
    assert not at.exception
    news_id = boton.key.removeprefix(f"{prefix}-test-")
    assert feedback.latest("test")[news_id]["verdict"] == verdict


@NEEDS_RESULTS
def test_aprobar_plan_cambia_la_tarjeta_y_los_kpis_y_se_puede_reabrir():
    at = run()
    sel = at.session_state["sel-test"]
    pending = int(kpi_value(at, "Alertas críticas"))
    at.button(key=f"ok-test-{sel}").click().run()
    assert int(kpi_value(at, "Alertas críticas")) == pending - 1
    assert "✓ PLAN APROBADO" in html(at) and "1 con plan aprobado" in html(at)
    assert any(b.key == f"re-test-{sel}" for b in at.button)         # confirmación + «Reabrir»
    at.button(key=f"re-test-{sel}").click().run()
    assert int(kpi_value(at, "Alertas críticas")) == pending
    assert sel not in feedback.active("test") and feedback.latest("test")[sel]["verdict"] == "reabierta"


@NEEDS_RESULTS
def test_falsa_alarma_saca_la_alerta_de_la_exposicion():
    at = run()
    sel = at.session_state["sel-test"]
    exposed = int(kpi_value(at, "Proveedores expuestos"))
    at.button(key=f"fa-test-{sel}").click().run()
    assert not at.exception
    assert int(kpi_value(at, "Proveedores expuestos")) < exposed
    assert "FALSA ALARMA · DESCARTADA" in html(at)


@NEEDS_RESULTS
def test_aprobar_desde_la_ventana_de_la_alerta():
    at = run()
    sel = at.session_state["sel-test"]
    at.button(key=f"qbtn-{sel}").click().run()
    at.button(key=f"dlg-ok-test-{sel}").click().run()
    assert not at.exception, at.exception
    assert feedback.latest("test")[sel]["verdict"] == "plan_aprobado"
    assert f"dlg-ok-test-{sel}" not in {b.key for b in at.button}      # la ventana se ha cerrado
    assert "✓ PLAN APROBADO" in html(at)


@NEEDS_RESULTS
def test_falsa_alarma_guarda_el_motivo():
    at = run()
    sel = at.session_state["sel-test"]
    at.text_input(key=f"fanote-test-{sel}").input("El proveedor confirma que no le afecta")
    at.button(key=f"fa-test-{sel}").click().run()
    assert not at.exception, at.exception
    assert feedback.latest("test")[sel]["note"] == "El proveedor confirma que no le afecta"
    assert "Motivo: «El proveedor confirma que no le afecta»" in html(at)


@NEEDS_RESULTS
def test_crear_pedido_y_recordatorio_y_marcarlos_como_hechos():
    at = run()
    sel = at.session_state["sel-test"]
    at.button(key=f"qbtn-{sel}").click().run()
    next(b for b in at.button if b.label == "Crear pedido").click().run()
    assert not at.exception, at.exception
    (order,) = [x for x in tasks.items("test", feedback.connect()) if x["kind"] == "order"]
    assert order["news_id"] == sel and order["status"] == "pendiente_erp" and order["quantity"] > 0
    at.button(key=f"qbtn-{sel}").click().run()
    next(b for b in at.button if b.label == "Crear recordatorio").click().run()
    assert not at.exception, at.exception
    at = run()                                            # la página, ya sin la ventana
    page = html(at)
    assert "📦 Pedido creado" in page and "⏰ Recordatorio" in page            # en la tarjeta
    assert "Acciones en curso" in page and "Pedido pendiente de envío al ERP" in page
    at.button(key=f"done-order-{order['id']}").click().run()
    assert not at.exception, at.exception
    assert next(x for x in tasks.items("test", feedback.connect()) if x["kind"] == "order")["status"] == "hecho"
    assert "📦 Pedido hecho" in html(at)


def test_pedido_sugerido_necesidad_mensual_por_dias_de_deficit():
    from core.countdown import Countdown
    from core.suppliers import load_suppliers
    sup = load_suppliers()
    # Kaveri (S002): 45 d de stock, el proveedor tarda 90 d en recuperarse; su alternativo no llega a tiempo
    c = Countdown("S002", "Kaveri", 45, "S001", False, 0, 60, False, 45, 90, False, "", -45, 45, "rotura_prevista",
                  [], "1200 kg")
    d = tasks.suggest_order(c, sup["S002"], "critica", today=date(2026, 10, 20))
    assert d.quantity == 1800 and d.unit == "kg"                 # 1200 kg/mes × 45 días / 30
    assert d.supplier_id == "S001"                               # el plan pide envío urgente al alternativo
    assert d.needed_by == date(2026, 12, 4) and d.priority == "Alta"
    assert "1.200 kg/mes × 45 días de déficit / 30 = 1.800 kg" in d.calc
    with pytest.raises(ValueError):
        tasks.create_order("test", "N1", "S001", "x", "x", 0, "kg", date.today(), "Alta", con=feedback.connect())


@NEEDS_RESULTS
def test_una_fila_del_ranking_abre_la_ficha():
    at = run("suppliers")
    at.button(key="rkbtn-S012").click().run()
    assert not at.exception, at.exception
    assert html(at).count(">Nordic Lipids AS</h2>") == 1              # en la ventana, no en la página


@NEEDS_RESULTS
def test_el_buscador_de_proveedores_abre_la_ficha():
    at = run("suppliers")
    at.selectbox(key="sup_pick").set_value("S025").run()
    assert not at.exception, at.exception
    assert ">Celsius Bioprocess Systems</h2>" in html(at)
    assert at.session_state["sup_pick"] is None                        # el buscador queda vacío


def test_pulsar_un_punto_del_mapa_pide_la_ficha():
    # Plotly devuelve el punto pulsado con customdata[0] = ID del proveedor
    def script():
        import streamlit as st
        from ui import sheet
        st.session_state["map-0"] = {"selection": {"points": [{"customdata": ["S025", "Celsius", ""]}]}}
        sheet._picked("map", 0)
        st.session_state["got_map"] = st.session_state.pop("sheet")
        st.session_state["map-1"] = {"selection": {"points": [{"id": "cat-API"}]}}    # algo que no es un proveedor
        sheet._picked("map", 1)
        st.session_state["got_other"] = st.session_state.get("sheet")
    at = AppTest.from_function(script).run()
    assert not at.exception, at.exception
    assert at.session_state["got_map"] == "S025" and at.session_state["got_other"] is None
    assert at.session_state["map-v"] == 2              # gráfico nuevo: el mismo punto se puede volver a pulsar


def test_treemap_agrupa_lo_que_no_tiene_riesgo_y_toda_casilla_lleva_nombre():
    from core.suppliers import load_suppliers
    from ui.treemap import GROUP, H, W, MIN_SHARE, layout, squarify
    rects = squarify([6, 6, 4, 3, 2, 2, 1], 0, 0, 600, 400)
    assert abs(sum(w * h for _, _, w, h in rects) - 600 * 400) < 1e-6
    sup = load_suppliers()
    tm = layout({"S025": "critica", "S002": "vigilar"})
    covered = [i for t in tm["tiles"] for i in t["ids"]]
    assert sorted(covered) == sorted(i for i, s in sup.items() if (s.annual_spend_eur or 0) > 0)   # todo el gasto
    assert {t["id"] for t in tm["tiles"] if not t["id"].startswith(GROUP)} >= {"S025", "S002"}
    assert sum(t["id"].startswith(GROUP) for t in tm["tiles"]) <= 3      # el resto, agrupado
    celsius = next(t for t in tm["tiles"] if t["id"] == "S025")
    assert "crítica" in celsius["aria"] and "Pulsa para ver la ficha" in celsius["aria"]   # estado en texto
    assert all("<b>" in t["html"] for t in tm["tiles"])                  # ninguna casilla sin nombre
    area = [t["w"] / 100 * W * t["h"] for t in tm["tiles"]]
    assert min(area) >= 0.9 * MIN_SHARE * W * H                          # tamaño mínimo
    assert all(0 <= t["x"] and t["x"] + t["w"] <= 100.01 and t["y"] + t["h"] <= H + 0.01 for t in tm["tiles"])


def _facts(news_id="N024"):
    from ui.comms_view import facts
    from ui.data import build_alerts
    return facts(next(a for a in build_alerts(results.load("test")["results"]) if a.id == news_id))


@NEEDS_RESULTS
def test_plantilla_de_comunicaciones_sin_cifras_inventadas():
    from core import comms
    from ui.comms_view import facts
    from ui.data import build_alerts
    for a in build_alerts(results.load("test")["results"]):
        f = facts(a)
        d = comms.template(f)
        assert comms.check(d, f) == [], a.id
        assert ("partial allocation" in d.email_body) == f.ask_partial
        assert f"{f.spend_meur} M€" in d.note and "Plan recomendado" in d.note


@NEEDS_RESULTS
def test_comunicaciones_detectan_cifras_inventadas_y_datos_internos():
    from core import comms
    f = _facts("N024")            # Celsius: proveedor único, el plan pide una asignación parcial
    ok = comms.Written(email_subject="Bioreactor bags: status", summary_es="Escasez de 12 semanas.",
                       email_body="Dear team, what is the status, when will supply resume and can you offer a "
                                  "partial allocation? Regards")
    assert comms.issues(ok, f) == []
    assert comms.issues(ok.model_copy(update={"summary_es": "Retraso de 9 semanas."}), f)       # 9: inventado
    leak = ok.model_copy(update={"email_body": ok.email_body + " Our stock covers 40 days."})
    assert any("internal" in x for x in comms.issues(leak, f))                                    # revela el stock
    no_partial = ok.model_copy(update={"email_body": "Dear team, what is the status? Regards"})
    assert comms.issues(no_partial, f) == ["ask for a partial allocation"]


@NEEDS_RESULTS
def test_comunicaciones_con_ia_que_inventa_usa_la_plantilla(monkeypatch):
    from core import comms, llm
    f = _facts("N024")
    bad = comms.Written(email_subject="Status", email_body="Please reply within 3 days. partial allocation?",
                        summary_es="Faltan 7 semanas.")
    monkeypatch.setattr(llm, "extract", lambda *a, **k: bad)
    p = comms.prepare(f, use_llm=True)
    assert p.source == "plantilla" and p.attempts == 2 and "3" in p.reason
    good = bad.model_copy(update={"email_body": "Subject: x\nDear team, status and restart date? Could you offer "
                                                "a partial allocation?", "summary_es": "Escasez de 12 semanas."})
    monkeypatch.setattr(llm, "extract", lambda *a, **k: good)
    p = comms.prepare(f, use_llm=True)
    assert p.source == "ia" and not p.drafts.email_body.startswith("Subject")
    assert "Resumen: Escasez de 12 semanas." in p.drafts.note and "−44 días" in p.drafts.note   # cifras del código


@NEEDS_RESULTS
def test_preparar_comunicaciones_y_marcar_como_enviado():
    at = run()
    sel = at.session_state["sel-test"]
    at.button(key=f"qbtn-{sel}").click().run()
    at.button(key=f"cmgo-test-{sel}").click().run()                  # sin Ollama: plantilla
    assert not at.exception, at.exception
    assert at.session_state[f"cm-info-test-{sel}"]["source"] == "plantilla"
    assert "Dear" in at.text_area(key=f"cm-mail-test-{sel}").value
    assert "Gasto anual" in at.text_area(key=f"cm-note-test-{sel}").value
    at.button(key=f"cmsent-correo-test-{sel}").click().run()
    assert not at.exception, at.exception
    (c,) = [x for x in tasks.items("test", feedback.connect()) if x["kind"] == "comm"]
    assert c["channel"] == "correo" and c["news_id"] == sel and c["source"] == "plantilla"
    assert "✉ Comunicado" in html(at)


@NEEDS_RESULTS
def test_modo_demo_noticia_entrante_y_reiniciar():
    at = run()
    assert not any(b.key == "demo-go" for b in at.button)            # sin modo demo, no hay botón
    critical, exposed = int(kpi_value(at, "Alertas críticas")), int(kpi_value(at, "Proveedores expuestos"))
    at.toggle(key="demo").set_value(True).run()
    at.button(key="demo-go").click().run()               # sin Ollama: el resultado precalculado
    assert not at.exception, at.exception
    assert at.session_state["demo_new"] == demo.FEED[0] == at.session_state["sel-test"]
    assert int(kpi_value(at, "Alertas críticas")) == critical + 1          # Nordic Lipids: urgente
    assert int(kpi_value(at, "Proveedores expuestos")) == exposed + 1
    assert "● NUEVA" in html(at) and "1 de 10 noticias" in html(at)
    at.button(key=f"ok-test-{demo.FEED[0]}").click().run()            # una decisión en la demo...
    con = demo.connect()
    assert [r["news_id"] for r in demo.injected(con)] == [demo.FEED[0]]
    assert feedback.latest("test", con)[demo.FEED[0]]["verdict"] == "plan_aprobado"
    assert feedback.latest("test") == {}                                   # ...no toca la base del panel
    at.button(key="demo-reset").click().run()
    assert int(kpi_value(at, "Alertas críticas")) == critical and demo.injected(con) == []
    assert feedback.latest("test", con) == {} and "● NUEVA" not in html(at)


@NEEDS_RESULTS
def test_simular_noticia_avisa_a_los_compradores_registrados_y_telegram_apagado_no_rompe_nada():
    from core import subscriptions as subs
    con = demo.connect()
    subs.register(111, "B1", con=con)               # Nordic Lipids es proveedor habitual de B1
    at = run()
    at.toggle(key="demo").set_value(True).run()
    at.button(key="demo-go").click().run()
    assert not at.exception, at.exception
    (n,) = subs.sent(demo.FEED[0], con)
    assert (n["chat_id"], n["kind"]) == (111, "urgente")
    for _ in range(50):                             # el envío va en segundo plano: sin token, «error»
        if subs.sent(demo.FEED[0], con)[0]["status"] != "enviando":
            break
        import time
        time.sleep(0.1)
    assert subs.sent(demo.FEED[0], con)[0]["status"] == "error"
    at.button(key="demo-reset").click().run()
    assert subs.sent(con=con) == [] and subs.buyer(111, con)          # el chat sigue registrado


@NEEDS_RESULTS
def test_sin_token_el_panel_muestra_telegram_desactivado():
    at = run()
    assert not at.exception, at.exception
    assert "Telegram desactivado (sin token)" in html(at)


@NEEDS_RESULTS
def test_sin_internet_el_panel_muestra_telegram_desactivado(monkeypatch):
    import requests
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:FALSO")

    def sin_red(*a, **k):
        raise requests.ConnectionError("sin red")
    monkeypatch.setattr(requests, "post", sin_red)
    at = run()
    assert not at.exception, at.exception
    assert "Telegram desactivado (sin conexión)" in html(at)


@NEEDS_RESULTS
def test_detalle_ventana_y_ficha_muestran_proveedor_habitual_y_pedido_en_transito():
    at = run()
    at.session_state["sel-test"] = "N024"            # Celsius: pedido mensual con 90 días de plazo
    at.run()
    page = html(at)
    assert re.search(r"Proveedor habitual · \d+ pedidos", page) and "En tránsito: <strong>" in page
    at.button(key="qbtn-N024").click().run()          # la ventana de la alerta
    assert not at.exception, at.exception
    assert html(at).count("Proveedor habitual ·") >= 2
    del at.session_state["alert_dialog"]             # una sola ventana a la vez
    at.session_state["sheet"] = "S037"               # alternativo con pedidos puntuales: no es habitual
    at.run()
    assert not at.exception, at.exception
    assert re.search(r"Pedidos puntuales · \d pedidos?", html(at))


@NEEDS_RESULTS
def test_enlace_de_telegram_abre_la_alerta():
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.query_params["alert"] = "N024"
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["alert_dialog"] == ("test", "N024") and at.session_state["sel-test"] == "N024"
    assert "alert" not in at.query_params


@NEEDS_RESULTS
def test_calendario_respeta_falsa_alarma_y_modo_demo():
    at = run("calendar")
    assert not at.exception, at.exception
    page = html(at)
    assert "Semáforo de medicamentos" in page and "Proyección desde hoy" in page
    roturas = int(kpi_value(at, "Rotura prevista"))
    assert roturas >= 1
    # Celsius (N024) descartada como falsa alarma: el HX-mAb deja de estar en rotura
    feedback.save("test", "N024", "falsa_alarma")
    at = run("calendar")
    assert int(kpi_value(at, "Rotura prevista")) == roturas - 1
    assert "1 descartadas como falsa alarma no cuentan" in html(at)
    # Modo demo: Nordic Lipids (N008, margen negativo) aparece también en el calendario
    con = demo.connect()
    demo.save(con, demo.precomputed("N008"), "precalculado", 0.1)
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.session_state["demo"] = True
    at.run()
    at.switch_page("views/calendar.py").run()
    assert not at.exception, at.exception
    assert int(kpi_value(at, "Rotura prevista")) == roturas + 1       # la base de la demo no tiene la falsa alarma


@NEEDS_RESULTS
def test_calendario_crear_pedido_desde_el_semaforo():
    at = run("calendar")
    at.button(key="sem-order-0").click().run()                 # el medicamento en peor estado
    assert not at.exception, at.exception
    iso, mid = at.session_state["cal_day"]
    assert iso == date.today().isoformat() and mid
    assert "Eventos del día" in html(at)
    next(b for b in at.button if b.label == "Crear pedido" and not (b.key or "").startswith("sem-")).click().run()
    assert not at.exception, at.exception
    (o,) = [x for x in tasks.items("test", feedback.connect()) if x["kind"] == "order"]
    assert o["status"] == "pendiente_erp" and o["quantity"] > 0
    assert not o["news_id"].startswith("cal-")                 # el peor material tiene alerta: queda enlazado a ella
    from ui.calendar_view import active_countdowns, events
    from core.order_calendar import plan
    mats, _ = plan(active_countdowns("test")[1], date.today())  # el pedido sale en el calendario, en su fecha
    evs = events(mats, tasks.items("test", feedback.connect()), date.today())
    assert any(e["k"] == "pedido" for e in evs.get(o["needed_by"], []))


def test_calendario_si_ya_no_llega_a_tiempo_pide_hoy_con_envio_urgente():
    # Lumina (S015) parada 60 d con 35 d de stock; su alternativo Vitrum tarda 50 d: llegaría 15 d tarde
    from core.countdown import Countdown
    from core.order_calendar import plan
    from ui.calendar_view import _deadline_text, events
    today = date.today()
    c = Countdown("S015", "Lumina", 35, "S016", False, 0, 50, False, 35, 60, False, "", -25, 25, "rotura_prevista",
                  [], "")
    mats, meds = plan([c], today)
    m = next(x for x in mats if x.material.id == "M11")
    assert _deadline_text(m) == "Pedir hoy con envío urgente · llegaría 15 días tarde"
    evs = events(mats, [], today)
    (e,) = [x for x in evs[today.isoformat()] if x["k"] == "pedir"]                # el marcador va a hoy
    assert "pedir hoy con envío urgente · llegaría 15 días tarde" in e["f"]
    assert not any(x["k"] == "pedir" for x in evs.get(m.deadline.isoformat(), []))   # no en una fecha pasada


def test_pedido_de_reposicion_desde_el_calendario():
    from core.countdown import Countdown
    from core.order_calendar import materials, material_plan
    today = date(2026, 10, 21)
    m = next(x for x in materials() if x.id == "M03")          # atorvastatina, 80 kg/mes
    d = tasks.suggest_restock(material_plan(m, [], today), today)
    assert d.supplier_id == "S004" and d.quantity == 80 and "un mes de necesidad" in d.calc
    assert d.needed_by == date(2026, 12, 20) and d.priority == "Baja"   # hoy + 60 d de stock
    c = Countdown("S004", "Orion", 60, "S005", True, 0, 80, False, 60, 90, False, "", -30, 30, "rotura_prevista",
                  [], "")
    d = tasks.suggest_restock(material_plan(m, [c], today), today)     # rotura del día 60 al 90
    assert d.quantity == 80 and "30 días de déficit" in d.calc and d.priority == "Alta"


def test_demo_guion_sin_etiquetas_y_en_orden(tmp_path):
    con = demo.connect(tmp_path / "d.db")
    n = demo.next_news(con)
    assert n["News_ID"] == demo.FEED[0] and "Is_Risk" not in n and "Explanation" not in n
    r = demo.precomputed(n["News_ID"])
    assert "gold" not in r
    demo.save(con, r, "precalculado", 0.1)
    assert demo.next_news(con)["News_ID"] == demo.FEED[1] and demo.progress(con) == (1, len(demo.FEED))
    demo.reset(con)
    assert demo.progress(con) == (0, len(demo.FEED))


@NEEDS_RESULTS
@pytest.mark.skipif(not scenario.EXAMPLES_PATH.exists(), reason="faltan data/scenarios.json")
def test_simulador_sin_ollama_usa_los_ejemplos_precalculados():
    at = run("simulator")
    assert at.text_area(key="sc_text").disabled and at.button(key="sc_interpret").disabled
    gujarat = next(i for i, e in enumerate(scenario.load_examples()) if "Gujarat" in e["text"])
    at.selectbox(key="sc_example").set_value(gujarat)
    at.button(key="sc_use_example").click().run()
    next(b for b in at.button if b.label == "Calcular impacto").click().run()
    assert not at.exception, at.exception
    calc = scenario.Scenario.model_validate(at.session_state["sc_calc"])
    assert scenario.simulate(calc).supplier_ids == ["S002", "S006", "S014"]
    assert "Kaveri Fine Chemicals" in html(at) and "Plan recomendado" in html(at)


@NEEDS_RESULTS
def test_simulador_interpreta_con_el_llm_y_se_puede_corregir(monkeypatch):
    from core import llm
    monkeypatch.setattr(llm, "is_up", lambda *a, **k: True)
    fake = scenario.Scenario(title="Cierre de Rotterdam", event_type="logistics_disruption", countries=[],
                             regions=[], cities=["Rotterdam"], categories=[], materials=[],
                             duration_value=10, duration_unit="days")
    monkeypatch.setattr(llm, "extract", lambda *a, **k: fake)
    at = run("simulator")
    at.text_area(key="sc_text").input("¿Y si cierra el puerto de Rotterdam 10 días?")
    at.button(key="sc_interpret").click().run()
    assert not at.exception, at.exception
    assert "sc_calc" not in at.session_state         # primero se muestra el escenario: no se calcula solo
    # El usuario corrige la duración antes de calcular
    next(n for n in at.number_input if n.label == "Duración (días)").set_value(20)
    next(b for b in at.button if b.label == "Calcular impacto").click().run()
    calc = scenario.Scenario.model_validate(at.session_state["sc_calc"])
    assert calc.duration_days == 20 and scenario.simulate(calc).supplier_ids == ["S030", "S038"]


@NEEDS_RESULTS
def test_fuente_de_noticias_por_defecto_cargadas_y_vuelta(monkeypatch):
    from core import custom_news
    at = run()
    assert "Noticias del día" in html(at)
    assert not [s for s in at.selectbox if s.key == "split_widget"]      # ya no hay selector de conjunto
    custom_news.process([{"News_ID": "X001", "Published_Date": "2026-10-20", "Source": "Reuters",
                          "Headline": "Fire at Taizhou chemical park forces evacuation of several API plants",
                          "Summary": "A fire broke out at a chemical park in Taizhou."}], name="n.xlsx",
                        use_llm=False)
    custom_news.use(True)
    at = run()
    assert "Noticias cargadas · n.xlsx" in html(at) and "Taizhou Hengyuan Pharma" in html(at)
    assert at.session_state["sel-custom"] == "X001"
    at = run("settings")
    assert not at.exception, at.exception
    assert "Cargar noticias" in {b.label for b in at.button}
    next(b for b in at.button if b.label == "Volver a las noticias del día").click().run()
    assert not custom_news.active() and "Noticias del día" in html(run())


@NEEDS_RESULTS
def test_ajustes_se_guardan_al_cambiarlos_y_se_restablecen():
    from core import settings
    at = run("settings")
    assert not at.exception, at.exception
    page = html(at)
    for text in ("Noticias", "IA", "Criterios de riesgo", "Notificaciones", "Datos y demo"):
        assert text in page
    at.number_input(key="set-margin").set_value(30).run()
    at.number_input(key="set-urgent-days").set_value(10).run()
    at.radio(key="set-mode").set_value("En el resumen").run()
    at.toggle(key="set-live").set_value(False).run()
    assert settings.load()["margin_tight_days"] == 30 and settings.get("urgent_buy_days") == 10
    assert settings.get("urgent_mode") == "resumen" and settings.get("live_ai") is False
    at.button(key="set-reset").click().run()
    assert not at.exception, at.exception
    assert settings.load() == settings.DEFAULTS
    assert at.number_input(key="set-margin~1").value == 14 and at.toggle(key="set-live~1").value is True


@NEEDS_RESULTS
def test_ajustes_reiniciar_demo_conserva_los_chats():
    from core import subscriptions
    con = demo.connect()
    subscriptions.register(111, "B1", "prueba", con=con)
    demo.save(con, {"news_id": "N008"}, "cache", 1.0)
    assert demo.progress(con)[0] == 1
    at = run("settings")
    at.button(key="set-demo-reset").click().run()
    assert not at.exception, at.exception
    assert demo.progress(con)[0] == 0 and subscriptions.buyer(111, con) is not None
