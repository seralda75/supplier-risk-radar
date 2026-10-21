"""Calendario de pedidos: fecha límite para pedir, proveedor que se usaría y estado de cada material y
medicamento (core/order_calendar.py)."""
from datetime import date, timedelta

from core.countdown import Countdown
from core.order_calendar import materials, plan

TODAY = date(2026, 10, 21)


def cd(sid, inv, ttr, margin, tts=None, alt_id=None, alt_affected=False, alt_lead=None, products=()):
    tts = inv if tts is None else tts
    return Countdown(sid, sid, inv, alt_id, alt_affected, 0, alt_lead, False, tts, ttr, False, "", margin,
                     max(0, -margin), "rotura_prevista" if margin < 0 else "cubierto", list(products), "")


def by_id(mats):
    return {m.material.id: m for m in mats}


def test_sin_alertas_fecha_limite_es_stock_menos_plazo():
    mats, meds = plan([], TODAY)
    m = by_id(mats)["M03"]                       # atorvastatina, Orion (S004): 60 d de stock, 45 d de plazo
    assert m.supplier_id == "S004" and not m.using_alternate
    assert m.deadline == TODAY + timedelta(days=60 - 45) and m.days_left == 15
    assert m.status == "suficiente" and m.margin is None and m.stockout is None
    assert len(mats) == len(materials()) == 20


def test_poco_stock_frente_al_plazo_es_peligro():
    m = by_id(plan([], TODAY)[0])["M13"]         # blíster: 30 d de stock, 30 d de plazo (< 30 + 7)
    assert m.status == "peligro" and m.days_left == 0


def test_principal_afectado_se_pide_al_alternativo():
    # Lumina (S015) afectada; su alternativo Vitrum (S016) no: se pediría a Vitrum, con su plazo
    m = by_id(plan([cd("S015", 35, 7, 28, alt_id="S016", alt_lead=50)], TODAY)[0])["M11"]
    assert m.supplier_id == "S016" and m.using_alternate
    assert m.deadline == TODAY + timedelta(days=35 - 50)
    assert m.recovery == TODAY + timedelta(days=7) and m.alt_arrival == TODAY + timedelta(days=50)


def test_principal_y_alternativo_afectados_se_queda_el_principal():
    cds = [cd("S015", 35, 7, 28, alt_id="S016"), cd("S016", 35, 7, 28, alt_id="S015")]
    m = by_id(plan(cds, TODAY)[0])["M11"]
    assert m.supplier_id == "S015" and not m.using_alternate and m.alt_arrival is None


def test_margen_negativo_es_rotura_con_sus_fechas_y_el_medicamento_hereda_el_peor():
    # Celsius (S025): 40 d de stock y 84 d hasta recuperarse -> rotura el día 40
    mats, meds = plan([cd("S025", 40, 84, -44)], TODAY)
    m = by_id(mats)["M18"]
    assert m.status == "rotura" and m.stockout == TODAY + timedelta(days=40)
    assert m.recovery == TODAY + timedelta(days=84) and m.margin == -44
    med = next(x for x in meds if x.name == "HX-mAb 100 mg injection")
    assert med.status == "rotura" and med.worst is m and med.stockout_days == 40
    assert meds[0].status == "rotura"                         # el peor, primero


def test_alerta_con_poco_margen_es_peligro_aunque_sobre_stock():
    m = by_id(plan([cd("S004", 60, 50, 10)], TODAY)[0])["M03"]
    assert m.status == "peligro" and "10 días de margen" in m.why
    # Con margen holgado sigue «suficiente» si se pide al principal (su alternativo, Wuhan, tarda 80 d > 60 d de
    # stock: si solo estuviera afectado Orion, se pediría a Wuhan y estaría en peligro)
    both = [cd("S004", 60, 20, 40), cd("S005", 60, 20, 40)]
    assert by_id(plan(both, TODAY)[0])["M03"].status == "suficiente"
    assert by_id(plan(both[:1], TODAY)[0])["M03"].status == "peligro"


def test_una_alerta_sin_corte_no_cuenta():
    m = by_id(plan([cd("S004", 60, 0, 60)], TODAY)[0])["M03"]       # ttr 0: el proveedor no se para
    assert m.status == "suficiente" and m.margin is None
