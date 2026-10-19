"""El panel arranca sin errores con los resultados guardados, en todas las vistas y conjuntos, sin llamar al LLM."""
import pytest
from streamlit.testing.v1 import AppTest

from core import feedback, results, scenario
from core.config import ROOT

APP = ROOT / "app.py"
VIEWS = ["control", "suppliers", "simulator", "transparency"]
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
    monkeypatch.setattr(llm, "is_up", lambda: False)      # por defecto, como si Ollama estuviera apagado


def run(view="control", split="test"):
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.session_state["view"] = view
    at.session_state["split"] = split
    return at.run()


def html(at) -> str:
    return "\n".join(m.value for m in at.markdown)


@NEEDS_RESULTS
@pytest.mark.parametrize("view", VIEWS)
@pytest.mark.parametrize("split", list(results.SPLITS))
def test_cada_vista_arranca_en_cada_conjunto(view, split):
    at = run(view, split)
    assert not at.exception, at.exception
    assert {b.key for b in at.button} >= {f"nav-{v}" for v in VIEWS}


@NEEDS_RESULTS
def test_la_navegacion_cambia_de_vista():
    at = run()
    at.button(key="nav-suppliers").click().run()
    assert at.session_state["view"] == "suppliers" and "Ranking de vulnerabilidad" in html(at)


@NEEDS_RESULTS
def test_centro_de_control_en_lenguaje_de_negocio():
    page = html(run())
    for text in ("Requiere tu decisión", "¿Cuánto aguantamos?", "Dónde está el riesgo", "Plan recomendado",
                 "Alertas críticas", "Gasto anual expuesto", "del gasto total"):
        assert text in page
    # sin jerga: ni TTS/TTR ni IDs de proveedor en la vista de negocio
    assert "TTS" not in page and "TTR" not in page and "S025" not in page
    assert "Celsius Bioprocess Systems" in page and "días" in page


@NEEDS_RESULTS
def test_la_cola_selecciona_la_alerta():
    at = run()
    ids = [b.key.removeprefix("qbtn-") for b in at.button if b.key.startswith("qbtn-")]
    assert len(ids) >= 2
    at.button(key=f"qbtn-{ids[1]}").click().run()
    assert at.session_state["sel-test"] == ids[1]
    assert any(b.key == f"ok-test-{ids[1]}" for b in at.button)       # el detalle muestra esa alerta


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
    monkeypatch.setattr(llm, "is_up", lambda: True)
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
