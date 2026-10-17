"""Reglas, urgencia y formato de la entrega con casos del ENTRENAMIENTO."""
import pytest

from core.data import format_ids, parse_ids
from core.matching import find_candidates
from core.pipeline import assess
from core.rules import classify_event


def run(headline, summary=""):
    return assess({"News_ID": "T", "Headline": headline, "Summary": summary}, use_llm=False, log=False)


@pytest.mark.parametrize("headline, event", [
    ("Fire at Taizhou chemical park forces evacuation of several API plants", "fire_plant_incident"),
    ("Magnitude 6.8 earthquake strikes southern Taiwan", "natural_disaster"),
    ("Spanish truckers' association calls nationwide strike next week", "labour_strike"),
    ("Rating agency downgrades Iberia Starch & Sugars to B-", "financial_distress"),
    ("Veltrix Pharma agrees to acquire syringe maker Kansai PreFill", "acquisition"),
    ("PolarChain Logistics chief executive steps down", "leadership_change"),
    ("Sunrise BioChem completes US inspection with no observations", "positive_news"),
    ("Central bank holds interest rates steady", "not_relevant"),
])
def test_tipo_de_evento(headline, event):
    assert classify_event(headline)[0] == event


def test_noticia_positiva_lleva_el_id_sin_riesgo():
    r = run("Sunrise BioChem completes US inspection with no observations",
            "Sunrise BioChem Ltd said a recent inspection of its Hyderabad site by US regulators was closed "
            "with no observations.")
    assert (r.is_risk, r.urgent, r.affected_ids) == (False, False, ["S001"])


def test_nombre_trampa_no_es_riesgo():
    r = run("Sunrise Energy commissions 500 MW solar farm in Rajasthan",
            "Renewable developer Sunrise Energy has switched on one of India's largest solar farms.")
    assert not r.is_risk and r.affected_ids == []


def test_huelga_de_transporte_no_afecta_a_servicios():
    r = run("Spanish truckers' association calls nationwide strike next week",
            "A major Spanish truckers' association has called a three-day nationwide strike over fuel prices, "
            "threatening road freight from industrial areas including Barcelona and Valencia.")
    assert r.is_risk and "S035" not in r.affected_ids and {"S011", "S018"} <= set(r.affected_ids)


def test_incendio_en_proveedor_unico_es_urgente():
    r = run("Fire at Taizhou chemical park forces evacuation of several API plants",
            "A fire at the Taizhou Coastal Chemical Park on Tuesday forced the evacuation of several facilities, "
            "including Taizhou Hengyuan Pharma's metformin production line. Officials expect safety inspections "
            "to last at least three weeks.")
    assert r.urgent and r.affected_ids == ["S003"]
    assert "ÚNICO" in r.action


def test_rebaja_de_rating_es_riesgo_no_urgente():
    r = run("Rating agency downgrades Iberia Starch & Sugars to B-",
            "A credit rating agency downgraded Iberia Starch & Sugars citing high debt and falling profits.")
    assert r.is_risk and not r.urgent


def test_solo_un_riesgo_puede_ser_urgente():
    r = run("Central bank holds interest rates steady")
    assert r.to_row() == {"Is_Risk": "N", "Urgent": "N", "Affected_Supplier_IDs": ""}


def test_formato_de_ids():
    assert format_ids(["S007", "S003", "S007"]) == "S003; S007"
    assert parse_ids("S039; S009") == ["S039", "S009"]
    assert parse_ids(float("nan")) == []
