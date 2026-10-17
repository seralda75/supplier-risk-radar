"""Generación de candidatos: casos del ENTRENAMIENTO (nunca de validación ni test)."""
import pytest

from core.matching import brand, core_name, find_candidates, normalize


def ids(headline, summary=""):
    return {c.id for c in find_candidates(headline, summary)}


def cand(headline, summary, sid):
    return next(c for c in find_candidates(headline, summary) if c.id == sid)


def test_normalize_quita_tildes_y_signos():
    assert normalize("Köln & Zürich's") == " koln and zurich s "


def test_core_name_quita_sufijos_societarios():
    assert core_name("Polaris Films Sp. z o.o.") == "polaris films"
    assert core_name("Nordic Lipids AS") == "nordic lipids"
    assert core_name("Iberia Starch & Sugars") == "iberia starch and sugars"


def test_marca_no_es_un_toponimo():
    assert brand("Gujarat Minerals & Salts") == "gujarat minerals"
    assert brand("Lumina Glassworks") == "lumina"


@pytest.mark.parametrize("headline, summary, sid", [
    ("'Lumina' tops the box office in its opening weekend",
     "The science fiction film Lumina earned USD 85 million in its first weekend in cinemas.", "S015"),
    ("Celtic beat Rangers 2-1 in Glasgow derby", "Celtic came from behind to win the Old Firm derby.", "S008"),
    ("Orion Capital raises USD 2 billion for new technology fund", "", "S004"),
])
def test_nombres_trampa_salen_como_ambiguos(headline, summary, sid):
    c = cand(headline, summary, sid)
    assert c.ambiguous_name and not c.named


def test_nombre_completo_no_es_ambiguo():
    c = cand("Celtic BioLogics doubles drug substance capacity at Cork site", "", "S008")
    assert c.named and not c.ambiguous_name


@pytest.mark.parametrize("headline, summary, expected", [
    ("Severe flooding in Gujarat disrupts industrial estates around Ahmedabad and Vadodara", "",
     {"S002", "S006", "S014"}),
    ("Low water on the Rhine restricts barge traffic for chemical shippers", "", {"S009", "S039"}),
    ("Hurricane Delia makes landfall in Puerto Rico, island-wide power outages", "", {"S025"}),
    ("Magnitude 6.8 earthquake strikes southern Taiwan", "", {"S013"}),
    ("Strike at Rotterdam container terminals enters third day", "", {"S030", "S038"}),
    ("Shipping lines reroute around Africa as Red Sea tensions escalate", "", {"S032"}),
])
def test_riesgo_por_ubicacion_sin_nombrar_al_proveedor(headline, summary, expected):
    assert expected <= ids(headline, summary)


def test_pais_sobra_si_hay_region_concreta():
    # "sur de Taiwán" concreta la zona: Hsinchu (norte) no debe colarse solo por el país
    assert "S027" not in ids("Magnitude 6.8 earthquake strikes southern Taiwan")


def test_us_en_minusculas_no_es_un_pais():
    assert not {"S017", "S029"} & ids("Shipping costs worry us", "Analysts told us prices will rise.")
