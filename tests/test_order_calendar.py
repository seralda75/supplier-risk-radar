"""Calendario de pedidos (core/order_calendar.py): se asume reposición regular salvo los proveedores con una
alerta activa; para esos, estado y fecha límite para pedir = día en que se acaba el stock − plazo del pedido de
emergencia (el alternativo o, sin él, la compra urgente del plan)."""
from datetime import date, timedelta

from core.countdown import Countdown
from core.order_calendar import URGENTE_DIAS, materials, plan

TODAY = date(2026, 10, 21)


def cd(sid, inv, ttr, margin, tts=None, alt_id=None, alt_affected=False, alt_lead=None, status=None):
    tts = inv if tts is None else tts
    status = status or ("rotura_prevista" if margin < 0 else "cubierto")
    return Countdown(sid, sid, inv, alt_id, alt_affected, 0, alt_lead, False, tts, ttr, False, "", margin,
                     max(0, -margin), status, [], "")


def by_id(mats):
    return {m.material.id: m for m in mats}


def days(n):
    return TODAY + timedelta(days=n)


def test_sin_alertas_todo_suficiente_y_la_cobertura_solo_informa():
    mats, meds = plan([], TODAY)
    assert len(mats) == len(materials()) == 20
    assert all(m.status == "suficiente" and m.deadline is None and not m.affected for m in mats)
    assert all(d.status == "suficiente" and d.deadline is None for d in meds)
    m = by_id(mats)["M02"]                      # metformina: 30 d de stock frente a 75 d de plazo, sin alarma
    assert m.stock_days == 30 and "reposición regular" in m.why


def test_margen_negativo_es_rotura_y_sin_alternativo_se_cuenta_la_compra_urgente():
    # Celsius (S025), proveedor único: 40 d de stock, 84 d hasta recuperarse
    mats, meds = plan([cd("S025", 40, 84, -44)], TODAY)
    m = by_id(mats)["M18"]
    assert m.status == "rotura" and m.urgent_buy and not m.using_alternate
    assert m.deadline == days(40 - URGENTE_DIAS) and m.days_left == 33 and m.late_days == 0
    assert m.stockout == days(40) and m.recovery == days(84)
    med = next(x for x in meds if x.name == "HX-mAb 100 mg injection")
    assert med.status == "rotura" and med.worst is m and med.deadline == m.deadline and med.stockout_days == 40
    assert meds[0] is med                                     # el peor, primero


def test_con_alternativo_libre_la_fecha_limite_resta_su_plazo_y_puede_llegar_tarde():
    # Lumina (S015) parada 60 d con 35 d de stock; su alternativo Vitrum (S016) tarda 50 d
    m = by_id(plan([cd("S015", 35, 60, -25, alt_id="S016", alt_lead=50)], TODAY)[0])["M11"]
    assert m.supplier_id == "S016" and m.using_alternate and not m.urgent_buy
    assert m.deadline == days(35 - 50) and m.days_left == -15 and m.late_days == 15   # «llegaría 15 días tarde»
    assert m.alt_arrival == days(50)


def test_alternativo_tambien_afectado_compra_urgente():
    cds = [cd("S015", 35, 60, -25, alt_id="S016", alt_affected=True, alt_lead=50), cd("S016", 35, 60, -25)]
    m = by_id(plan(cds, TODAY)[0])["M11"]
    assert m.urgent_buy and m.deadline == days(35 - URGENTE_DIAS) and m.alt_arrival is None


def test_margen_de_0_a_14_dias_es_peligro():
    m = by_id(plan([cd("S004", 60, 70, 10, alt_id="S005", alt_lead=80)], TODAY)[0])["M03"]
    assert m.status == "peligro" and "10 días de margen" in m.why
    assert m.deadline == days(60 - 80)                     # el stock se acaba antes de que Orion vuelva


def test_riesgo_latente_es_peligro_no_rotura():
    m = by_id(plan([cd("S002", 45, 90, -45, status="riesgo_latente")], TODAY)[0])["M01"]
    assert m.status == "peligro" and "riesgo latente" in m.why and m.stockout == days(45)


def test_alerta_cubierta_no_alarma_ni_pide():
    # Lumina vuelve en 7 d y hay 35 d de stock: no hace falta pedir aunque el alternativo tarde 50 d
    m = by_id(plan([cd("S015", 35, 7, 28, alt_id="S016", alt_lead=50)], TODAY)[0])["M11"]
    assert m.status == "suficiente" and m.affected and m.deadline is None and "cubierta" in m.why
    assert m.recovery == days(7) and m.alt_arrival is None


def test_una_alerta_sin_corte_no_cuenta():
    m = by_id(plan([cd("S004", 60, 0, 60)], TODAY)[0])["M03"]       # ttr 0: el proveedor no se para
    assert m.status == "suficiente" and not m.affected and m.margin is None
