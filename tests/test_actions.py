"""La acción recomendada tiene en cuenta la cuenta atrás (sin llamar a Ollama)."""
from core.actions import recommend_action
from core.schemas import NewsAssessment


def risk(ids, event="fire_plant_incident", recovery=None, soon=True, unit="days"):
    return NewsAssessment(evidence="x", affected_ids=ids, event_type=event, is_risk=True, severity=4,
                          stops_supply_soon=soon, recovery_value=recovery,
                          recovery_unit=unit if recovery is not None else None, confidence=0.9)


def test_alternativo_que_no_llega_a_tiempo_no_es_la_solucion_principal():
    # S001: 45 días de inventario; su alternativo S002 tarda 60 en entregar; recuperación 60 días
    text = recommend_action(risk(["S001"], recovery=60), urgent=True)
    assert "activar YA" not in text and "no llega a tiempo" in text
    assert "déficit de 15 días" in text
    assert "envío urgente" in text and "compra puntual" in text and "reasignar stock" in text
    assert "Amoxira 500 mg capsules" in text


def test_alternativo_que_llega_a_tiempo_se_activa():
    # S009: 40 días de inventario; S010 entrega en 30; recuperación 45 -> margen +5 con el alternativo
    text = recommend_action(risk(["S009"], recovery=45), urgent=True)
    assert "activar YA el alternativo S010" in text and "déficit" not in text


def test_alternativo_a_tiempo_pero_insuficiente_indica_el_deficit():
    # S009 con recuperación de 90 días: 40 + 10 del alternativo = 50 -> déficit de 40
    text = recommend_action(risk(["S009"], recovery=90), urgent=True)
    assert "activar YA el alternativo S010" in text and "no basta" in text and "déficit de 40 días" in text


def test_alternativo_afectado_por_el_mismo_evento_no_se_propone():
    text = recommend_action(risk(["S009", "S010"], recovery=60), urgent=True)
    assert "activar" not in text and "también está afectado" in text and "déficit de 20 días" in text


def test_proveedor_unico_con_deficit():
    text = recommend_action(risk(["S003"], recovery=60), urgent=True)
    assert text.startswith("ACTUAR YA.") and "ÚNICO" in text and "déficit de 30 días" in text


def test_si_el_inventario_cubre_el_alternativo_queda_en_reserva():
    text = recommend_action(risk(["S015"], event="labour_strike", recovery=7), urgent=False)
    assert "cubre por sí solo" in text and "margen +28 d" in text and "S016 queda en reserva" in text
    assert "déficit" not in text


def test_riesgo_latente_se_avisa_aunque_no_sea_urgente():
    text = recommend_action(risk(["S002"], event="regulatory_action"), urgent=False)
    assert text.startswith("No urgente, pero con riesgo latente") and "déficit de 45 días" in text


def test_logistica_sin_inventario_deriva_al_alternativo():
    text = recommend_action(risk(["S030"], event="labour_strike", recovery=5), urgent=True)
    assert "impacto inmediato durante 5 d" in text and "Derivar los envíos al alternativo S031" in text


def test_sin_riesgo_no_hay_accion():
    a = risk(["S001"]).model_copy(update={"is_risk": False})
    assert recommend_action(a, urgent=False).startswith("Ninguna acción")


# ---------------------------------------------------------------------------
# Plan en pasos (centro de control): misma lógica que el texto, con responsable y plazo
# ---------------------------------------------------------------------------
from core.actions import plan_steps, situation          # noqa: E402
from core.countdown import countdown                      # noqa: E402
from core.suppliers import load_suppliers                 # noqa: E402


def plan(ids, urgent=True, **kw):
    [c] = countdown(risk(ids, **kw), urgent)
    s = load_suppliers()[c.supplier_id]
    return situation(c, s), plan_steps(c, s, urgent)


def test_plan_si_el_alternativo_no_llega_a_tiempo():
    case, steps = plan(["S001"], recovery=60)
    assert case == "alt_tarde"
    assert "envío urgente" in steps[0].text and "Kaveri Fine Chemicals" in steps[0].text
    assert not any(x.text.startswith("Activar el pedido") for x in steps)
    assert any("faltan 15 días" in x.text for x in steps)
    assert [x.owner for x in steps] == ["Compras", "Planificación", "Logística", "Calidad"]


def test_plan_de_proveedor_unico_con_deficit_como_el_mockup():
    case, steps = plan(["S025"], event="supply_shortage", recovery=12, unit="weeks")
    assert case == "unico_deficit" and len(steps) == 3
    assert steps[0].when == "hoy" and "asignación parcial" in steps[0].text
    assert "HX-mAb 100 mg inyectable" in steps[1].text and "faltan 44 días" in steps[1].text
    assert steps[2].owner == "Calidad"


def test_plan_con_alternativo_a_tiempo_lo_activa():
    case, steps = plan(["S009"], recovery=45)
    assert case == "alt_a_tiempo" and steps[0].text.startswith("Activar el pedido a Lombardia Polymers SpA")


def test_plan_no_urgente_relaja_los_plazos():
    _, steps = plan(["S002"], urgent=False, event="regulatory_action")
    assert {x.when for x in steps} <= {"esta semana", "2 semanas"}
