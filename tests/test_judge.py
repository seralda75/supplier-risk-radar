"""Salvaguardas deterministas sobre la salida del LLM (sin llamar a Ollama)."""
import math

from core.judge import apply_guards
from core.matching import find_candidates
from core.schemas import NewsAssessment
from core.urgency import combine_with_rules


def verdict(**kw):
    base = dict(evidence="x", affected_ids=[], event_type="not_relevant", is_risk=False, severity=1,
                stops_supply_soon=False, recovery_days=None, confidence=0.9)
    return NewsAssessment(**{**base, **kw})


def test_confidence_en_porcentaje_se_normaliza():
    assert verdict(confidence=80).confidence == 0.8


def test_confidence_ambigua_entre_1_y_5_se_rechaza():
    # qwen2.5 devolvía 4 (nota de 1 a 5) y el validador lo convertía en 0.04
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        verdict(confidence=4)
    assert verdict(confidence=1).confidence == 1.0


def test_no_se_inventan_ids():
    cands = find_candidates("Strike at Rotterdam container terminals enters third day")
    a = apply_guards(verdict(affected_ids=["S030", "S038", "S019"], event_type="labour_strike", is_risk=True,
                             severity=2), cands)
    assert a.affected_ids == ["S030", "S038"]


def test_noticia_positiva_conserva_el_proveedor_nombrado():
    h = "Sunrise BioChem completes US inspection with no observations"
    a = apply_guards(verdict(event_type="positive_news"), find_candidates(h))
    assert a.affected_ids == ["S001"] and not a.is_risk


def test_sin_riesgo_no_lleva_ids_solo_por_ubicacion():
    h = "Cork airport passenger numbers reach record"
    a = apply_guards(verdict(affected_ids=["S008"]), find_candidates(h))
    assert a.affected_ids == []


def test_huelga_de_transporte_no_afecta_al_software():
    h = "Spanish truckers' association calls nationwide strike in Madrid, Barcelona and Valencia"
    a = apply_guards(verdict(affected_ids=["S011", "S018", "S035"], event_type="labour_strike", is_risk=True,
                             severity=2), find_candidates(h))
    assert "S035" not in a.affected_ids


def test_gravedad_combinada_redondea_hacia_arriba():
    a = combine_with_rules(verdict(is_risk=True, affected_ids=["S017"], severity=3), 4, True)
    assert a.severity == math.ceil(3.5) and a.stops_supply_soon


def test_nombre_ambiguo_sin_contexto_se_descarta():
    # trampa del entrenamiento (N030): aunque el LLM aceptara el nombre, la salvaguarda lo quita
    h = "Celtic beat Rangers 2-1 in Glasgow derby"
    a = apply_guards(verdict(affected_ids=["S008"], event_type="other_risk", is_risk=True, severity=2),
                     find_candidates(h), h)
    assert a.affected_ids == [] and not a.is_risk


def test_nombre_ambiguo_con_contexto_se_mantiene():
    h = "Celtic BioLogics doubles drug substance capacity at Cork site"
    a = apply_guards(verdict(event_type="positive_news"), find_candidates(h), h)
    assert a.affected_ids == ["S008"]


def test_restriccion_a_la_exportacion_es_urgente_aunque_sea_temporal():
    from core.suppliers import load_suppliers
    from core.urgency import dependency, is_urgent
    a = verdict(is_risk=True, affected_ids=["S002"], event_type="export_restriction", severity=3,
                stops_supply_soon=False)
    assert is_urgent(a, [dependency(load_suppliers()["S002"])])[0]


def test_politica_de_desempate_es_explicita():
    from core.pipeline import TIEBREAK
    assert set(TIEBREAK) == {"Is_Risk", "Urgent", "Affected_Supplier_IDs"}
    assert set(TIEBREAK.values()) <= {"llm", "reglas"}
