"""El panel arranca sin errores con los resultados guardados, en los tres conjuntos, sin llamar al LLM."""
import pytest
from streamlit.testing.v1 import AppTest

from core import feedback, results, scenario
from core.config import ROOT

APP = ROOT / "app.py"
NEEDS_RESULTS = pytest.mark.skipif(not results.path("test").exists(),
                                   reason="faltan data/results (scripts/build_results.py)")


@pytest.fixture(autouse=True)
def db_temporal(tmp_path, monkeypatch):
    # las respuestas de los botones van a una base de datos temporal, no a data/app.db
    monkeypatch.setattr(feedback, "DB_PATH", tmp_path / "test.db")


@pytest.fixture(autouse=True)
def sin_llm(monkeypatch):
    from core import llm

    def prohibido(*a, **k):
        raise AssertionError("El panel no debe llamar al LLM")
    monkeypatch.setattr(llm, "extract", prohibido)
    monkeypatch.setattr(llm, "chat", prohibido)
    monkeypatch.setattr(llm, "is_up", lambda: False)      # por defecto, como si Ollama estuviera apagado


@NEEDS_RESULTS
@pytest.mark.parametrize("split", list(results.SPLITS))
def test_panel_arranca_en_cada_conjunto(split):
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.session_state["split"] = split
    at.run()
    assert not at.exception, at.exception
    assert len(at.tabs) == 5


@NEEDS_RESULTS
def test_falsa_alarma_se_guarda_en_sqlite():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    boton = next(b for b in at.button if b.key.startswith("fa-test-"))
    boton.click().run()
    assert not at.exception
    news_id = boton.key.removeprefix("fa-test-")
    assert feedback.latest("test")[news_id]["verdict"] == "falsa_alarma"


def _boton(at, label):
    return next(b for b in at.button if b.label == label)


@NEEDS_RESULTS
@pytest.mark.skipif(not scenario.EXAMPLES_PATH.exists(), reason="faltan data/scenarios.json")
def test_simulador_sin_ollama_usa_los_ejemplos_precalculados():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert at.text_area(key="sc_text").disabled and at.button(key="sc_interpret").disabled
    gujarat = next(i for i, e in enumerate(scenario.load_examples()) if "Gujarat" in e["text"])
    at.selectbox(key="sc_example").set_value(gujarat)
    at.button(key="sc_use_example").click().run()
    _boton(at, "Calcular impacto").click().run()
    assert not at.exception, at.exception
    calc = scenario.Scenario.model_validate(at.session_state["sc_calc"])
    assert scenario.simulate(calc).supplier_ids == ["S002", "S006", "S014"]
    assert any("Kaveri Fine Chemicals" in str(df.value) for df in at.dataframe)


@NEEDS_RESULTS
def test_simulador_interpreta_con_el_llm_y_se_puede_corregir(monkeypatch):
    from core import llm
    monkeypatch.setattr(llm, "is_up", lambda: True)
    fake = scenario.Scenario(title="Cierre de Rotterdam", event_type="logistics_disruption", countries=[],
                             regions=[], cities=["Rotterdam"], categories=[], materials=[],
                             duration_value=10, duration_unit="days")
    monkeypatch.setattr(llm, "extract", lambda *a, **k: fake)
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    at.text_area(key="sc_text").input("¿Y si cierra el puerto de Rotterdam 10 días?")
    at.button(key="sc_interpret").click().run()
    assert not at.exception, at.exception
    assert "sc_calc" not in at.session_state         # primero se muestra el escenario: no se calcula solo
    # El usuario corrige la duración antes de calcular
    next(n for n in at.number_input if n.label == "Duración (días)").set_value(20)
    _boton(at, "Calcular impacto").click().run()
    calc = scenario.Scenario.model_validate(at.session_state["sc_calc"])
    assert calc.duration_days == 20 and scenario.simulate(calc).supplier_ids == ["S030", "S038"]
