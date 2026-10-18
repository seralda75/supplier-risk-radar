"""El panel arranca sin errores con los resultados guardados, en los tres conjuntos, sin llamar al LLM."""
import pytest
from streamlit.testing.v1 import AppTest

from core import feedback, results
from core.config import ROOT

APP = ROOT / "app.py"


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


@pytest.mark.skipif(not results.path("test").exists(), reason="faltan data/results (scripts/build_results.py)")
@pytest.mark.parametrize("split", list(results.SPLITS))
def test_panel_arranca_en_cada_conjunto(split):
    at = AppTest.from_file(str(APP), default_timeout=60)
    at.session_state["split"] = split
    at.run()
    assert not at.exception, at.exception
    assert len(at.tabs) == 4


@pytest.mark.skipif(not results.path("test").exists(), reason="faltan data/results (scripts/build_results.py)")
def test_falsa_alarma_se_guarda_en_sqlite():
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    boton = next(b for b in at.button if b.key.startswith("fa-test-"))
    boton.click().run()
    assert not at.exception
    news_id = boton.key.removeprefix("fa-test-")
    assert feedback.latest("test")[news_id]["verdict"] == "falsa_alarma"
