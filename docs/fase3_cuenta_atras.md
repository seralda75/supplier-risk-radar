# Fase 3 · Cuenta atrás (TTS − TTR)

**Pregunta de negocio:** si este proveedor deja de servir, ¿aguantamos hasta que se recupere?

| Concepto | Definición | Fuente |
|---|---|---|
| **TTS** (time to survive) | Días que Helixa puede seguir produciendo sin el proveedor | `Inventory_Cover_Days` + margen del alternativo |
| **TTR** (time to recover) | Días hasta que el proveedor vuelve a la normalidad | Duración escrita en la noticia (`recovery_value` + `recovery_unit` del juez, convertida a días por código), o un valor por defecto (estimado) |
| **Margen** | TTS − TTR | < 0: rotura de stock prevista (urgente) o **riesgo latente** (no urgente) · 0-13 d: margen ajustado · ≥ 14 d: cubierto |

Código: `core/countdown.py`. Tests: `tests/test_countdown.py`. **No cambia ninguna respuesta Y/N**:
la urgencia sigue saliendo de gravedad × dependencia (`core/urgency.py`); la cuenta atrás es
información para el comprador (detalle del test, panel y bot).

## Supuestos (constantes visibles y ajustables)

1. **Sin alternativo:** TTS = días de inventario, consumidos al ritmo habitual.
2. **Alternativo aprobado (`ALTERNATE_SHARE = 0,5`):** como ya está cualificado, se le hace un pedido
   el día 0; llega tras su `Lead_Time_Days` y desde entonces asume la mitad del volumen (supuesto
   conservador de capacidad libre). El inventario que queda cuando llega dura el doble:

   `margen del alternativo = max(0, inventario − plazo del alternativo) × 0,5 / (1 − 0,5)`

   - Si el plazo del alternativo supera el inventario, **no llega a tiempo** y no suma nada
     (por ejemplo S001: 45 días de inventario, pero su alternativo S002 tarda 60 en entregar).
     Tener alternativo "en el papel" no basta: es un hallazgo útil para el pitch y para la fase 8.2.
   - Si el alternativo está afectado por el mismo evento (S001 y S002 en India), tampoco suma.
3. **Logística y servicios (sin inventario):** no hay colchón; si hay interrupción, el impacto es
   inmediato durante el TTR (estado `sin_inventario`).
4. **TTR por defecto** cuando la noticia no da pistas (`DEFAULT_RECOVERY_DAYS`), marcado como
   *estimado*. Si el evento no para el suministro a corto plazo (efecto lento), TTR = 0. Son órdenes
   de magnitud generales, **no datos medidos ni cifras de mercado**; el cliente los sustituye por su
   histórico de incidentes:

   | Evento | Días | Evento | Días |
   |---|---|---|---|
   | Incendio / incidente en planta | 30 | Acción regulatoria | 90 |
   | Desastre natural | 30 | Retirada de lotes | 30 |
   | Corte de suministros (luz, agua) | 14 | Restricción a la exportación | 60 |
   | Huelga | 7 | Dificultades financieras | 90 |
   | Disrupción logística | 14 | Ciberataque | 14 |
   | Conflicto geopolítico | 60 | Escasez de suministro | 30 |
   | Adquisición / cambio de directivos | 0 | Otro riesgo | 30 |

5. **Umbral de margen ajustado (`MARGIN_TIGHT_DAYS = 14`):** unas dos semanas para gestionar un
   pedido urgente o un transporte alternativo.

## Riesgo latente

La cuenta atrás **no influye en la urgencia** (decisión del 18/10/2026): `Urgent` sigue siendo
gravedad × dependencia. Cuando una noticia **no es urgente pero el margen es negativo**, el estado
es `riesgo_latente`: no salta la alerta inmediata, pero el comprador ve que, si la recuperación dura
lo previsto, se acabaría el inventario. El resumen indica si el TTR viene de la noticia o es un
valor por defecto ("TTR estimado"), porque en el segundo caso la señal es mucho más débil.

## Duración de la recuperación

- El LLM devuelve la duración **tal como aparece en la noticia** (valor + unidad: horas, días,
  semanas o meses) y el código la convierte a días, redondeando hacia arriba (48 horas -> 2 días).
- Si la duración no está escrita en la noticia (`judge.duration_in_text`), se descarta y se usa el
  valor por defecto, marcado como estimado. Ver `docs/evaluacion.md`, v8.

## Salida

- `AssessmentResult.countdown`: por proveedor, inventario, alternativo (¿afectado?, días que suma),
  TTS, TTR (¿estimado?, de dónde sale), margen, estado, productos afectados (`Used_In_Products`) y
  necesidad mensual. También queda en el JSON de la auditoría.
- `test_detalle.csv`: columnas `Affected_Products`, `Countdown` (una línea por proveedor),
  `Min_Margin_Days` y `Countdown_Status` (el proveedor con menos margen).

## Acción recomendada según la cuenta atrás (`core/actions.py`)

Antes la acción solo miraba si había alternativo ("preparar la activación del alternativo") y podía
contradecir a la cuenta atrás: en N004 proponía activar S001, que tarda 60 días en entregar cuando el
inventario de S002 dura 45. Ahora la acción sale del margen de cada proveedor afectado:

| Situación | Acción |
|---|---|
| El inventario cubre por sí solo la recuperación | Confirmar stock y fecha de reanudación; el alternativo queda en reserva |
| El alternativo no está afectado y llega antes de que se acabe el inventario | Activarlo ya (con el margen resultante); si aun así no basta, déficit y medidas |
| El alternativo **no llega a tiempo** | No es la solución principal: déficit en días + envío urgente del alternativo, compra puntual (con cualificación de urgencia), reasignar stock, priorizar productos |
| El alternativo **también está afectado** | No se propone: déficit + compra puntual fuera de la zona, reasignar stock, priorizar productos |
| Proveedor único con déficit | Déficit + compra puntual, reasignar stock, priorizar productos |
| Sin inventario (logística, servicios) | Impacto inmediato durante el TTR: derivar al alternativo si no está afectado; si no, servicio puntual / plan de contingencia |

- **Días de déficit** = −margen (TTR − TTS) cuando hay inventario; en logística y servicios, el TTR
  completo. Nuevos campos de `Countdown`: `deficit_days`, `alternate_lead_days`, `alternate_in_time`.
- Una noticia no urgente con margen negativo empieza por "No urgente, pero con riesgo latente".
- No hay datos de criticidad clínica por producto: la acción nombra los productos afectados y deja la
  priorización entre ellos al comprador.
- **No cambia ninguna respuesta Y/N ni la urgencia** (comprobado: el Excel del test es idéntico).
  Cambian la columna `Action` de `test_detalle.csv` y los resultados del panel.

## Observaciones en la entrega del test

- **N016** (huelga de 48 horas en Antwerp-Bruges): antes el LLM devolvía 48 días y salía una rotura
  de −18 d. **Resuelto** en la v8: 48 horas -> 2 días, margen +28 d (cubierto).
- **N004** (warning letter a Kaveri): `Urgent = N` y margen −45 d con TTR estimado de 90 días ->
  `riesgo_latente · TTR estimado`. La noticia no da plazo; el valor por defecto de una acción
  regulatoria es pesimista a propósito y el cliente puede ajustarlo. La acción ya no propone activar
  S001 (tarda 60 d y el inventario dura 45): indica 45 días de déficit, envío urgente de S001,
  compra puntual, reasignar stock y reservar el stock para Amoxira.
- **N024** (Celsius, retrasos de 12 semanas): urgente y rotura prevista (−44 d) con un TTR que sí
  viene de la noticia: es el caso más claro para el comprador.
