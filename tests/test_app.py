"""El panel arranca sin errores con los resultados guardados, en todas las páginas y conjuntos, sin llamar
al LLM, y todo lo que se puede pulsar hace algo (inventario de elementos clicables en docs/panel.md)."""
import re

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from datetime import date

from core import feedback, results, scenario, tasks
from core.config import ROOT

APP = ROOT / "app.py"
PAGES = {"control": None, "suppliers": "views/suppliers.py", "simulator": "views/simulator.py",
         "transparency": "views/transparency.py"}
NAV = {"Centro de control": "", "Proveedores": "proveedores", "Simulador «¿Y si…?»": "simulador",
       "Transparencia": "transparencia"}
NEEDS_RESULTS = pytest.mark.skipif(not results.path("test").exists(),
                                   reason="faltan data/results (scripts/build_results.py)")


@pytest.fixture(autouse=True)
def db_temporal(tmp_path, monkeypatch):
    # las decisiones de los botones van a una base de datos temporal, no a data/app.db
    monkeypatch.setattr(feedback, "DB_PATH", tmp_path / "test.db")


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


def run(view="control", split="test"):
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.session_state["split"] = split
    at.run()
    if PAGES[view]:
        at.switch_page(PAGES[view]).run()
    return at


def html(at) -> str:
    return "\n".join(m.value for m in at.markdown)


def kpi_value(at, label: str) -> str:
    m = re.search(rf'<span class="k">{re.escape(label)}</span><span class="v"><span class="\w+"[^>]*>([^<]+)<',
                  html(at))
    assert m, label
    return m.group(1)


@NEEDS_RESULTS
@pytest.mark.parametrize("view", list(PAGES))
@pytest.mark.parametrize("split", list(results.SPLITS))
def test_cada_pagina_arranca_en_cada_conjunto(view, split):
    at = run(view, split)
    assert not at.exception, at.exception
    links = {(x.proto.label, x.proto.page) for x in at.get("page_link")}
    assert set(NAV.items()) <= links                      # el menú son enlaces reales a cada página


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
    for text in ("La noticia", "Impacto", "Calendario de", "Plan recomendado", "Acciones de esta alerta"):
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
