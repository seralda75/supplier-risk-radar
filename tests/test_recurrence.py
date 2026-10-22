"""Recurrencia de compra (core/recurrence.py): pedidos en 6 y 12 meses, meses seguidos, último pedido,
pedidos en tránsito y proveedor habitual = al menos 3 pedidos en 6 meses."""
from datetime import date, timedelta

from core.recurrence import (BUYERS, HISTORY_PATH, Order, buyers_of, by_buyer, load_history, months_back,
                             recurrence, recurrent_suppliers)

TODAY = date(2026, 10, 22)


def order(n, day, sid="S001", buyer="B1", lead=30, qty=100.0):
    return Order(f"PO-{n}", day, sid, "Amoxicillin trihydrate", qty, "kg", day + timedelta(days=lead), buyer)


def monthly(sid, buyer, days_of_month, lead=30, months=12, skip=()):
    """Un pedido al mes durante `months` meses hasta octubre de 2026 (saltando los meses de `skip`)."""
    out = []
    for i in range(months):
        y, m = divmod(2026 * 12 + 10 - 1 - i, 12)
        if (y, m + 1) in skip:
            continue
        out.append(order(f"{sid}-{i}", date(y, m + 1, days_of_month), sid, buyer, lead))
    return out


def test_meses_atras_respeta_el_fin_de_mes():
    assert months_back(TODAY, 6) == date(2026, 4, 22)
    assert months_back(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert months_back(date(2026, 1, 15), 12) == date(2025, 1, 15)


def test_pedido_mensual_es_habitual_con_pedido_en_transito():
    orders = monthly("S001", "B1", 21, lead=60)
    r = recurrence("S001", TODAY, orders=orders)
    assert (r.orders_6m, r.orders_12m, r.consecutive) == (6, 12, 12)
    assert r.recurrent
    assert r.last_order.day == date(2026, 10, 21)
    # con 60 días de plazo, los pedidos del 21 sep y del 21 oct aún no han llegado
    assert [o.day for o in r.in_transit] == [date(2026, 9, 21), date(2026, 10, 21)]
    assert r.next_arrival.arrival == date(2026, 11, 20)
    assert r.transit_quantity == 200


def test_si_el_pedido_de_este_mes_aun_no_se_ha_hecho_los_meses_seguidos_cuentan_desde_el_anterior():
    orders = [o for o in monthly("S001", "B1", 28) if o.day < TODAY]    # el de octubre (día 28) aún no
    r = recurrence("S001", TODAY, orders=orders)
    assert r.consecutive == 11 and r.recurrent


def test_un_hueco_corta_los_meses_seguidos():
    orders = monthly("S001", "B1", 5, skip={(2026, 8)})
    r = recurrence("S001", TODAY, orders=orders)
    assert r.consecutive == 2                    # septiembre y octubre
    assert r.orders_12m == 11


def test_dos_pedidos_puntuales_no_hacen_habitual_y_tres_en_seis_meses_si():
    two = [order(1, date(2026, 6, 6), "S037"), order(2, date(2026, 9, 1), "S037")]
    assert not recurrence("S037", TODAY, orders=two).recurrent
    three = two + [order(3, date(2026, 5, 1), "S037")]
    assert recurrence("S037", TODAY, orders=three).recurrent
    old = two + [order(3, date(2026, 4, 1), "S037")]              # fuera de los 6 meses
    r = recurrence("S037", TODAY, orders=old)
    assert (r.orders_6m, r.orders_12m, r.recurrent) == (2, 3, False)


def test_no_cuenta_pedidos_futuros_ni_los_ya_llegados_como_en_transito():
    orders = [order(1, date(2026, 9, 1), lead=10), order(2, date(2026, 11, 1), lead=10)]
    r = recurrence("S001", TODAY, orders=orders)
    assert r.orders_12m == 1 and r.in_transit == [] and r.last_order.id == "PO-1"


def test_sin_pedidos():
    r = recurrence("S999", TODAY, orders=[])
    assert (r.orders_6m, r.orders_12m, r.consecutive, r.last_order, r.in_transit) == (0, 0, 0, None, [])
    assert not r.recurrent and r.next_arrival is None


def test_por_comprador():
    orders = monthly("S001", "B1", 3) + monthly("S015", "B2", 3) + [order(9, date(2026, 6, 1), "S002", "B1")]
    assert recurrent_suppliers("B1", TODAY, orders) == ["S001"]
    assert [r.supplier_id for r in by_buyer("B1", TODAY, orders)] == ["S001", "S002"]
    assert recurrent_suppliers("B2", TODAY, orders) == ["S015"]
    assert buyers_of("S015", TODAY, orders) == ["B2"] and buyers_of("S002", TODAY, orders) == []
    # por comprador: los pedidos de otro comprador al mismo proveedor no cuentan
    assert recurrence("S015", TODAY, "B1", orders).orders_12m == 0


def test_el_historial_sintetico():
    orders = load_history()
    assert HISTORY_PATH.read_text(encoding="utf-8").startswith("# DATOS SINTÉTICOS")
    assert {o.buyer_id for o in orders} == set(BUYERS)
    ref = max(o.day for o in orders)               # el día de referencia con que se generó
    # todos los proveedores principales de la hoja Materials son habituales de su comprador
    assert "S003" in recurrent_suppliers("B1", ref) and "S015" in recurrent_suppliers("B2", ref)
    assert "S030" in recurrent_suppliers("B3", ref)
    # un alternativo con pedidos puntuales no lo es
    assert recurrence("S037", ref).orders_12m >= 1 and not recurrence("S037", ref).recurrent
