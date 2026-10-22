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

## 2. Recurrencia (`core/recurrence.py`)

Por proveedor, y opcionalmente por comprador, se calcula:
- los pedidos de los últimos 6 y 12 meses;
- los meses seguidos con pedido, hasta este mes (o el anterior, si el de este mes aún no se ha hecho);
- el último pedido;
- los pedidos en tránsito: ya hechos y aún sin llegar, con su cantidad y su llegada prevista.

Un proveedor es **habitual** con al menos 3 pedidos en 6 meses. Con el historial sintético lo son los 20
proveedores principales de la hoja Materials y los 7 de servicio. Los alternativos con pedidos puntuales no lo son.

## 3. Tablas en SQLite (`core/subscriptions.py`)

Las tablas están en la misma base que el resto del panel: `data/app.db`, o `data/demo.db` en el modo demo.
Ninguna toca la entrega ni los resultados.

| Tabla | Contenido |
|---|---|
| `buyers` | chat de Telegram → comprador ficticio elegido en `/start`. Pueden registrarse varios chats a la vez. |
| `subscriptions` | proveedores que sigue cada chat. `auto`: sus proveedores habituales, que se recrean solos; `manual`: los de `/seguir`. `/dejar` desactiva la fila sin borrarla. |
| `notifications` | un aviso por chat y alerta, para que nunca se repita. Los urgentes quedan como `enviado` o `error`; los no urgentes, como `pendiente` hasta el `/resumen`. Un aviso con error se reintenta. |

«Reiniciar demo» y `scripts/reset_demo.py` vacían `subscriptions` y `notifications`, pero conservan
`buyers`: los chats registrados no tienen que volver a hacer `/start`.

## 4. Bot (`bot/telegram_bot.py`)

Usa python-telegram-bot v21+ en modo polling, sin URL pública. El token se lee de `.env` con python-dotenv;
no se imprime y se tapa en los logs.

```powershell
.venv\Scripts\python -m bot.telegram_bot --demo    # con data/demo.db (la del «Modo demo» del panel)
.venv\Scripts\python -m bot.telegram_bot           # con data/app.db
```

Comandos:
- `/start`: elegir el comprador ficticio con botones.
- `/seguir <proveedor>` y `/dejar <proveedor>`: por ID o por nombre, por ejemplo «S015» o «Lumina».
- `/mis_proveedores`: los proveedores que sigues.
- `/resumen`: las alertas no urgentes de la semana.

El bot también atiende los botones de los avisos y envía cada recordatorio de «Recordarme mañana» el día
que vence.

## 5. Notificador (`bot/notifier.py`)

- **Interfaz `Channel`:** `available()` y `send_alert(chat_id, mensaje)`.
  - `TelegramChannel` usa la Bot API por HTTPS, con formato HTML y todo el texto escapado.
  - `WhatsAppChannel` es un esqueleto documentado, sin implementar: plantillas aprobadas por Meta, webhook
    público y coste por conversación. Añadir Teams sería escribir otra clase.
- **Quién recibe cada alerta:** por cada proveedor afectado, los chats suscritos a él. Son de forma
  automática los compradores para los que es habitual, más quien lo siga a mano. Si una alerta afecta a
  proveedores de varios compradores, cada uno recibe la parte que le toca.
- **Urgente:** el aviso sale al momento con el evento, la recurrencia, el pedido en tránsito, el margen, los
  medicamentos afectados y el plan. Lleva cuatro botones:
  - **Aprobar plan** y **Falsa alarma** quedan en `feedback` con `channel = telegram`, y el panel muestra
    «· desde Telegram».
  - **Recordarme mañana** crea un recordatorio en «Acciones en curso».
  - **Ver en el panel** abre `http://localhost:8501/?alert=<id>` (con `demo=1` en el modo demo). Telegram no
    admite enlaces a `localhost` en los botones; si lo rechaza, el enlace va en el texto del mensaje.
- **No urgente:** queda para `/resumen`.
- **Datos que no salen en el aviso:** el gasto, la cuota, la puntuación de calidad y el texto completo de la
  noticia.
- **Cuándo se dispara:**
  - «Simular noticia entrante», que muestra en el paso 5 a cuántos compradores se ha avisado;
  - `assess(noticia, notify="test")`;
  - `scripts/notify_alerts.py`, que avisa de las alertas ya calculadas. Admite `--demo` y `--dry-run`.

## 6. Robustez

- **Sin token o sin internet:** el panel funciona igual, el pie del menú muestra «Telegram desactivado (sin
  token)» o «(sin conexión)», y los avisos quedan con estado `error`.
- **Envío en segundo plano:** el aviso no frena la demo.
- **Errores:** un fallo de Telegram nunca rompe el panel ni el pipeline.

## 7. En el panel

La ficha del proveedor, el detalle de la alerta y su ventana muestran:
- «Proveedor habitual · N pedidos»: N son los pedidos de 12 meses, junto con los de 6 meses, los meses
  seguidos, el último pedido y el comprador;
- el pedido en tránsito;
- la nota «historial de pedidos sintético».
