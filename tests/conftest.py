"""Los tests nunca leen ni escriben los ajustes ni las noticias cargadas reales (data/settings.json, data/custom)."""
import pytest

from core import results, settings


@pytest.fixture(autouse=True)
def ajustes_temporales(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(results, "CUSTOM_DIR", tmp_path / "custom")
