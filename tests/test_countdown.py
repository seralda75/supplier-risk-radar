"""Cuenta atrás (TTS − TTR) con los datos reales de proveedores, sin llamar a Ollama."""
from core.countdown import DEFAULT_RECOVERY_DAYS, countdown, worst
from core.data import load_news
from core.pipeline import assess
from core.schemas import NewsAssessment


def risk(ids, event="fire_plant_incident", recovery=None, soon=True, unit="days", **kw):
    base = dict(evidence="x", affected_ids=ids, event_type=event, is_risk=True, severity=4,
                stops_supply_soon=soon, recovery_value=recovery,
                recovery_unit=unit if recovery is not None else None, confidence=0.9)
    return NewsAssessment(**{**base, **kw})


def test_proveedor_unico_sin_margen_de_alternativo():
    # S003: único, 30 días de inventario; la noticia dice 3 semanas -> margen +9, ajustado
    [c] = countdown(risk(["S003"], recovery=21))
    assert (c.tts_days, c.ttr_days, c.margin_days) == (30, 21, 9)
    assert c.status == "margen_ajustado" and not c.ttr_estimated
    assert c.products == ["Glucora 850 mg tablets"]


def test_alternativo_que_llega_a_tiempo_da_margen():
    # S009: 40 días de inventario; su alternativo S010 entrega en 30 -> (40 − 30) × 0,5 / 0,5 = 10 días más
    [c] = countdown(risk(["S009"], recovery=30))
    assert c.alternate_margin_days == 10 and c.tts_days == 50 and c.margin_days == 20
    assert c.status == "cubierto"


def test_alternativo_que_no_llega_a_tiempo_no_da_margen():
    # S001: 45 días de inventario; su alternativo S002 tarda 60 en entregar
    [c] = countdown(risk(["S001"], recovery=60))
    assert c.alternate_margin_days == 0 and c.margin_days == -15 and c.status == "rotura_prevista"


def test_margen_negativo_sin_urgencia_es_riesgo_latente():
    [c] = countdown(risk(["S001"], recovery=2, unit="months"), urgent=False)
    assert c.ttr_days == 60 and c.status == "riesgo_latente" and "TTR según la noticia" in c.summary()
    [c] = countdown(risk(["S002"], event="regulatory_action"), urgent=False)
    assert c.status == "riesgo_latente" and c.ttr_estimated and "TTR estimado" in c.summary()


def test_margen_positivo_sin_urgencia_no_es_riesgo_latente():
    [c] = countdown(risk(["S003"], recovery=21), urgent=False)
    assert c.status == "margen_ajustado"


def test_huelga_de_48_horas_no_son_48_dias():
    [c] = countdown(risk(["S022"], event="labour_strike", recovery=48, unit="hours"), urgent=False)
    assert c.ttr_days == 2 and c.status == "cubierto"


def test_alternativo_afectado_por_el_mismo_evento():
    cds = {c.supplier_id: c for c in countdown(risk(["S009", "S010"], recovery=30))}
    assert cds["S009"].alternate_affected and cds["S009"].alternate_margin_days == 0


def test_sin_recovery_days_usa_el_valor_por_defecto_y_lo_marca_estimado():
    [c] = countdown(risk(["S017"], event="quality_recall"))
    assert c.ttr_days == DEFAULT_RECOVERY_DAYS["quality_recall"] and c.ttr_estimated


def test_evento_lento_sin_recovery_days_no_interrumpe():
    [c] = countdown(risk(["S020"], event="acquisition", soon=False, severity=2))
    assert c.ttr_days == 0 and c.ttr_estimated and c.status == "cubierto"


def test_logistica_sin_inventario():
    [c] = countdown(risk(["S030"], event="labour_strike", recovery=3))
    assert c.status == "sin_inventario" and "impacto inmediato" in c.summary()


def test_logistica_sin_interrupcion_esta_cubierta():
    [c] = countdown(risk(["S032"], event="logistics_disruption", soon=False, severity=2))
    assert c.status == "cubierto" and "sin interrupción" in c.summary()


def test_sin_riesgo_no_hay_cuenta_atras():
    a = risk(["S001"], event="positive_news", is_risk=False, severity=1, soon=False)
    assert countdown(a) == []


def test_peor_margen():
    cds = countdown(risk(["S003", "S009"], recovery=21))
    assert worst(cds).supplier_id == "S003"


def test_la_cuenta_atras_no_cambia_las_respuestas():
    # Modo reglas sobre el entrenamiento: la decisión Y/N es la misma con o sin cuenta atrás
    from core.rules import assess_rules
    from core.matching import find_candidates
    from core.urgency import dependency, is_urgent
    from core.suppliers import load_suppliers
    for n in load_news("train"):
        r = assess(n, use_llm=False, log=False)
        a = assess_rules(n["Headline"], n["Summary"], find_candidates(n["Headline"], n["Summary"]))
        urgent, _ = is_urgent(a, [dependency(load_suppliers()[i]) for i in a.affected_ids])
        assert (r.is_risk, r.urgent, r.affected_ids) == (a.is_risk, urgent, sorted(a.affected_ids))
        assert bool(r.countdown) == r.is_risk


def test_revision_por_confianza_baja_en_modo_reglas():
    # el modo reglas declara confianza 0,6: sus riesgos van a revisión con el motivo confianza_baja
    n = next(x for x in load_news("train") if x["News_ID"] == "N001")
    r = assess(n, use_llm=False, log=False)
    assert r.needs_review and r.review_reasons == ["confianza_baja"]
