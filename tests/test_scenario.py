"""Simulador «¿Y si…?»: el cálculo lo hace el código (sin llamar a Ollama)."""
import pytest

from core import scenario
from core.scenario import Scenario, anchor_to_text, simulate


def S(**kw):
    base = dict(title="t", event_type="natural_disaster", countries=[], regions=[], cities=[], categories=[],
                materials=[], duration_value=None, duration_unit=None)
    return Scenario(**{**base, **kw})


def test_inundacion_en_gujarat_tres_semanas():
    imp = simulate(S(regions=["Gujarat"], duration_value=3, duration_unit="weeks"))
    assert imp.supplier_ids == ["S002", "S006", "S014"]
    assert all(c.ttr_days == 21 and not c.ttr_estimated for c in imp.countdowns)
    assert imp.spend_exposed == 1_800_000 + 900_000 + 250_000


def test_el_pais_de_una_region_no_amplia_el_alcance():
    # "Gujarat, India": las coincidencias solo por país sobran si ya hay una región concreta (como en las noticias)
    assert simulate(S(countries=["India"], regions=["Gujarat"])).supplier_ids == ["S002", "S006", "S014"]


def test_china_restringe_exportacion_de_api_sin_duracion_usa_ttr_estimado():
    imp = simulate(S(event_type="export_restriction", countries=["China"], categories=["API"]))
    assert imp.supplier_ids == ["S003", "S005", "S007"]
    assert set(imp.excluded) == {"S024", "S033"}
    s003 = next(c for c in imp.countdowns if c.supplier_id == "S003")
    assert s003.ttr_estimated and s003.deficit_days == 30          # único, 30 d de inventario, 60 d por defecto
    assert imp.products_table()[0] == {"product": "Glucora 850 mg tablets", "materials": ["Metformin hydrochloride"],
                                       "margin": -30.0, "status": "rotura_prevista", "deficit": 30.0}


def test_huelga_de_transporte_no_afecta_a_servicios():
    imp = simulate(S(event_type="labour_strike", countries=["España"], duration_value=5, duration_unit="days"))
    assert imp.supplier_ids == ["S011", "S018"] and imp.excluded == ["S035"]


def test_alternativo_afectado_a_la_vez_no_da_margen():
    # Rin: S009 (Ludwigshafen) afectado, su alternativo S010 (Milán) no -> le da margen
    imp = simulate(S(event_type="logistics_disruption", regions=["Rhine"], duration_value=1, duration_unit="months"))
    s009 = next(c for c in imp.countdowns if c.supplier_id == "S009")
    assert not s009.alternate_affected and s009.alternate_margin_days == 10
    # Excipientes de magnesio en Taiwán y Gujarat a la vez: S013 y S014 son alternativos entre sí
    imp = simulate(S(regions=["Gujarat", "southern Taiwan"], duration_value=60, duration_unit="days"))
    s013 = next(c for c in imp.countdowns if c.supplier_id == "S013")
    assert s013.alternate_affected and s013.deficit_days == 20
    assert any("también está afectado" in text for sid, text in imp.actions() if sid == "S013")


def test_material_concreto_manda_sobre_la_categoria():
    imp = simulate(S(event_type="supply_shortage", categories=["Primary packaging"], materials=["Type I glass vials"]))
    assert imp.supplier_ids == ["S015", "S016"]


def test_lugar_sin_proveedores_se_avisa():
    imp = simulate(S(countries=["Francia"], regions=["Atlantis"]))
    assert imp.hits == [] and imp.unmatched_places == ["Francia", "Atlantis"]
    assert simulate(S()).note        # sin lugar, categoría ni material no se puede delimitar


def test_nombres_en_espanol_y_materiales_se_normalizan():
    sc = S(countries=["Países Bajos", "EE. UU.", "Taiwán"], materials=["viales de vidrio", "metformina", "litio"])
    assert sc.countries == ["Netherlands", "USA", "Taiwan"]
    assert sc.materials == ["Type I glass vials", "Metformin hydrochloride", "litio"]


def test_restricciones_que_no_estan_en_el_texto_se_descartan():
    sc = S(event_type="labour_strike", countries=["Spain"], categories=["Logistics"],
           materials=["API", "Process solvents"])
    fixed, dropped = anchor_to_text(sc, "¿Y si hay una huelga de transportistas en España de 5 días?")
    assert fixed.categories == [] and fixed.materials == []
    assert set(dropped) == {"categoría Logistics", "categoría API", "material Process solvents"}
    fixed, dropped = anchor_to_text(S(materials=["API"]), "¿Y si China restringe la exportación de API?")
    assert fixed.categories == ["API"] and fixed.materials == [] and dropped == []


@pytest.mark.skipif(not scenario.EXAMPLES_PATH.exists(), reason="faltan data/scenarios.json")
def test_los_ejemplos_precalculados_son_validos_y_afectan_a_alguien():
    examples = scenario.load_examples()
    assert [e["text"] for e in examples] == scenario.EXAMPLES
    for e in examples:
        imp = simulate(e["scenario"])
        assert imp.hits and not imp.unmatched_places, e["text"]
