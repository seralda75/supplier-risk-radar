# Fase 6 · Avisos por Telegram a los compradores

## 1. Historial de pedidos (sintético)

Los datos del reto no incluyen historial de compras. Para saber qué proveedores son **habituales** de cada
comprador, `scripts/build_purchase_history.py` genera `data/purchase_history.csv`. Son **datos sintéticos**,
no del reto: así lo dicen la primera línea del CSV y este documento. Los Excel del reto no se modifican.

```powershell
.venv\Scripts\python scripts\build_purchase_history.py                  # 12 meses hasta hoy
.venv\Scripts\python scripts\build_purchase_history.py --hoy 2026-10-23 # con otro día de referencia
```

Reglas, con semilla fija (42); con el mismo día de referencia se obtiene el mismo fichero:

- **Pedido regular:** un pedido al mes durante 12 meses, por material (hoja Materials) y a su proveedor
  principal. La cantidad es `Monthly_Requirement` ± 10 %, y la llegada es la fecha del pedido más los
  `Lead_Time_Days` de la hoja Suppliers.
- **En tránsito:** un pedido está en tránsito si su llegada prevista es posterior al día de referencia. Con plazos
  de más de un mes puede haber varios a la vez; por ejemplo, Celtic BioLogics tarda 120 días y tiene 4 en camino.
- **Pedidos puntuales:** algunos alternativos reciben 1 o 2 pedidos de entre el 20 y el 40 % del consumo mensual.
  No llegan a ser proveedores habituales.
- **Servicios:** logística, servicios y los proveedores sin fila en Materials no tienen `Monthly_Requirement`.
  Reciben un pedido mensual de servicio (cantidad 1). Si dos proveedores son alternativos entre sí, solo lo recibe
  el de más gasto anual.
- **Comprador:** cada pedido lo hace el comprador ficticio del área del proveedor (`core/recurrence.BUYERS`):

| Comprador | Área | Categorías de proveedor |
|---|---|---|
| B1 Lucía Herrera | APIs y excipientes | API, Excipients, Chemicals, Single-use bioprocess, Lab reagents |
| B2 Pablo Navarro | Envases | Primary packaging, Secondary packaging |
| B3 Irene Campos | Logística y servicios | Logistics, Services, Consumables |

Columnas: `order_id, order_date, kind (regular | puntual | servicio), supplier_id, supplier_name,
supplier_category, material_id, material, quantity, unit, lead_time_days, expected_arrival, status, buyer_id,
buyer_name, buyer_area`. La columna `status` refleja el día de referencia. La recurrencia, en cambio, vuelve a
calcular qué pedidos están en tránsito a partir de las fechas y del día de hoy.
