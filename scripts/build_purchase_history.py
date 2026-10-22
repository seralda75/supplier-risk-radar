"""Genera un historial de pedidos SINTÉTICO (data/purchase_history.csv). Los datos del reto no lo traen.

    python scripts/build_purchase_history.py                  # 12 meses hasta hoy
    python scripts/build_purchase_history.py --hoy 2026-10-23

Con semilla fija (SEED): mismo día de referencia -> mismo fichero. Reglas:
- Un pedido al mes, durante 12 meses, por material (hoja Materials) a su proveedor principal, con la cantidad
  de Monthly_Requirement ± 10 % y la llegada a los Lead_Time_Days de la hoja Suppliers. Está «en tránsito» si
  aún no ha llegado el día de referencia (con plazos de más de un mes, puede haber varios a la vez).
- Algunos alternativos reciben 1 o 2 pedidos puntuales (20-40 % del mes): no son proveedores habituales.
- Logística, servicios y los proveedores sin fila en Materials (sin Monthly_Requirement): un pedido mensual
  de servicio (cantidad 1) al de más gasto de cada pareja de alternativos.
- Cada pedido lo hace el comprador ficticio del área del proveedor (core/recurrence.BUYERS).
No modifica los Excel del reto.
"""
from __future__ import annotations

import argparse
import csv
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import TRAIN_XLSX                          # noqa: E402
from core.recurrence import BUYERS, HISTORY_PATH, buyer_for  # noqa: E402

SEED = 42
MONTHS = 12
SERVICE_UNIT = {"Logistics": "servicio", "Services": "servicio"}
COLUMNS = ["order_id", "order_date", "kind", "supplier_id", "supplier_name", "supplier_category", "material_id",
           "material", "quantity", "unit", "lead_time_days", "expected_arrival", "status", "buyer_id",
           "buyer_name", "buyer_area"]


def monthly_dates(today: date, day: int, n: int) -> list[date]:
    """Los n últimos días `day` de cada mes que no pasan de hoy (del más antiguo al más reciente)."""
    y, m = today.year, today.month
    if day > today.day:                      # el pedido de este mes aún no se ha hecho
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    out = []
    for _ in range(n):
        out.append(date(y, m, day))
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    return out[::-1]


def rounded(q: float, unit: str) -> float:
    """Cantidad con tres cifras significativas; las unidades, enteras."""
    step = 10 ** max(0, math.floor(math.log10(q)) - 2) if q >= 1 else 0.1
    if unit == "units":
        step = max(step, 1)
    v = round(q / step) * step
    return int(v) if float(v).is_integer() else round(v, 1)


def build(today: date) -> list[dict]:
    rng = random.Random(SEED)
    sup = pd.read_excel(TRAIN_XLSX, sheet_name="Suppliers").set_index("Supplier_ID")
    mat = pd.read_excel(TRAIN_XLSX, sheet_name="Materials")
    rows: list[dict] = []

    def add(d: date, kind: str, sid: str, mid: str, name: str, qty: float, unit: str) -> None:
        s = sup.loc[sid]
        lead = 0 if pd.isna(s.Lead_Time_Days) else int(s.Lead_Time_Days)
        arrival = d + timedelta(days=lead)
        b = buyer_for(s.Category)
        rows.append({"order_date": d.isoformat(), "kind": kind, "supplier_id": sid, "supplier_name": s.Supplier_Name,
                     "supplier_category": s.Category, "material_id": mid, "material": name, "quantity": qty,
                     "unit": unit, "lead_time_days": lead, "expected_arrival": arrival.isoformat(),
                     "status": "en_transito" if arrival > today else "entregado", "buyer_id": b,
                     "buyer_name": BUYERS[b]["name"], "buyer_area": BUYERS[b]["area"]})

    # 1. Materiales: pedido mensual al principal y algún pedido puntual al alternativo
    for m in mat.itertuples(index=False):
        for d in monthly_dates(today, rng.randint(1, 28), MONTHS):
            q = m.Monthly_Requirement * min(1.1, max(0.9, rng.gauss(1, 0.05)))
            add(d, "regular", m.Primary_Supplier_ID, m.Material_ID, m.Material, rounded(q, m.Unit), m.Unit)
        if not pd.isna(m.Alternate_Supplier_ID) and rng.random() < 0.5:
            for back in sorted(rng.sample(range(30, 360), rng.randint(1, 2)), reverse=True):
                q = m.Monthly_Requirement * rng.uniform(0.2, 0.4)
                add(today - timedelta(days=back), "puntual", m.Alternate_Supplier_ID, m.Material_ID, m.Material,
                    rounded(q, m.Unit), m.Unit)
    # 2. Proveedores sin fila en Materials: servicio mensual al de más gasto de cada pareja
    in_materials = set(mat.Primary_Supplier_ID) | set(mat.Alternate_Supplier_ID.dropna())
    for sid, s in sup.iterrows():
        if sid in in_materials:
            continue
        alt = None if pd.isna(s.Approved_Alternate_ID) else s.Approved_Alternate_ID
        if alt and sup.loc[alt].Annual_Spend_EUR > s.Annual_Spend_EUR:
            continue
        for d in monthly_dates(today, rng.randint(1, 28), MONTHS):
            add(d, "servicio", sid, "", s.Material_Supplied, 1, SERVICE_UNIT.get(s.Category, "lote"))

    rows.sort(key=lambda r: (r["order_date"], r["supplier_id"]))
    for i, r in enumerate(rows, 1):
        r["order_id"] = f"PO-{i:04d}"
    return rows


def write(rows: list[dict], today: date, path: Path = HISTORY_PATH) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        f.write(f"# DATOS SINTÉTICOS: no proceden del reto. Generados por scripts/build_purchase_history.py "
                f"(semilla {SEED}) con referencia {today.isoformat()}.\n")
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hoy", type=date.fromisoformat, default=date.today(), help="día de referencia (AAAA-MM-DD)")
    args = ap.parse_args()
    rows = build(args.hoy)
    write(rows, args.hoy)
    transit = sum(r["status"] == "en_transito" for r in rows)
    print(f"{HISTORY_PATH}: {len(rows)} pedidos ({transit} en tránsito), referencia {args.hoy}")


if __name__ == "__main__":
    main()
