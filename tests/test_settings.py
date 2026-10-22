"""Ajustes del panel (data/settings.json): valores, validación y, sobre todo, que no cambian la entrega.
El conftest los redirige a una carpeta temporal."""
import hashlib
import subprocess
import sys

from core import order_calendar, results, settings
from core.config import ROOT
from core.data import load_news
from core.pipeline import assess

EXTREMOS = dict(margin_tight_days=60, urgent_buy_days=1, recurrent_min=6, urgent_mode="resumen",
                live_ai=False, ai_timeout_s=10)


def test_valores_por_defecto_guardar_y_restablecer():
    assert settings.load() == settings.DEFAULTS
    assert settings.DEFAULTS["margin_tight_days"] == 14 and settings.DEFAULTS["urgent_buy_days"] == 7
    assert settings.DEFAULTS["recurrent_min"] == 3
    settings.save(margin_tight_days=30, urgent_mode="resumen")
    assert settings.get("margin_tight_days") == 30 and settings.get("urgent_mode") == "resumen"
    settings.save(source="custom")
    settings.reset()
    assert settings.get("margin_tight_days") == 14 and settings.get("urgent_mode") == "inmediato"
    assert settings.get("source") == "custom"                 # la fuente de noticias tiene su propio botón


def test_valida_y_no_se_rompe_con_un_fichero_editado_a_mano():
    assert settings.save(margin_tight_days=999)["margin_tight_days"] == 60      # dentro de los límites
    assert settings.save(urgent_mode="otra")["urgent_mode"] == "inmediato"
    settings.SETTINGS_PATH.write_text("{ no es json", encoding="utf-8")
    assert settings.load() == settings.DEFAULTS
    settings.SETTINGS_PATH.write_text('{"margin_tight_days": "mucho", "live_ai": 3}', encoding="utf-8")
    assert settings.load() == settings.DEFAULTS


def _entrega() -> list[dict]:
    """La respuesta del pipeline a las 20 noticias del test (modo reglas: determinista y sin GPU)."""
    return [assess(n, use_llm=False, log=False).model_dump() for n in load_news("test")]


def test_los_ajustes_no_cambian_la_entrega():
    entrega = [results.path(s) for s in results.SPLITS]
    antes = [hashlib.md5(p.read_bytes()).hexdigest() for p in entrega if p.exists()]
    por_defecto = _entrega()
    settings.save(**EXTREMOS)
    assert _entrega() == por_defecto                           # el diagnóstico es el mismo con cualquier ajuste
    assert [hashlib.md5(p.read_bytes()).hexdigest() for p in entrega if p.exists()] == antes


def test_pipeline_y_fill_test_no_dependen_de_los_ajustes():
    """Ni el pipeline, ni evaluate.py, ni fill_test.py cargan core.settings (ni lo hace nada de lo que importan)."""
    code = ("import sys, core.pipeline, core.countdown, core.urgency, core.judge, fill_test, evaluate;"
            "print('core.settings' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT)
    assert out.returncode == 0, out.stderr[-400:]
    assert out.stdout.strip() == "False"


def test_los_ajustes_si_cambian_el_calendario_del_panel():
    from tests.test_order_calendar import TODAY, by_id, cd, days
    celsius = [cd("S025", 40, 84, -44)]                  # proveedor único: se cuenta la compra urgente
    assert by_id(order_calendar.plan(celsius, TODAY)[0])["M18"].deadline == days(40 - 7)
    settings.save(urgent_buy_days=20)
    assert by_id(order_calendar.plan(celsius, TODAY)[0])["M18"].deadline == days(40 - 20)
    margen_12 = [cd("S015", 35, 20, 12, alt_id="S016", alt_lead=10)]
    assert by_id(order_calendar.plan(margen_12, TODAY)[0])["M11"].status == "peligro"   # 12 d <= 14 d
    settings.save(margin_tight_days=5)
    assert by_id(order_calendar.plan(margen_12, TODAY)[0])["M11"].status == "suficiente"
