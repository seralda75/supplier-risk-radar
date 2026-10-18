# Fase 3 · Cuenta atrás (TTS − TTR)

**Pregunta de negocio:** si este proveedor deja de servir, ¿aguantamos hasta que se recupere?

| Concepto | Definición | Fuente |
|---|---|---|
| **TTS** (time to survive) | Días que Helixa puede seguir produciendo sin el proveedor | `Inventory_Cover_Days` + margen del alternativo |
| **TTR** (time to recover) | Días hasta que el proveedor vuelve a la normalidad | `recovery_days` del juez LLM, o un valor por defecto (estimado) |
| **Margen** | TTS − TTR | < 0: rotura de stock prevista · 0-13 d: margen ajustado · ≥ 14 d: cubierto |

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

## Salida

- `AssessmentResult.countdown`: por proveedor, inventario, alternativo (¿afectado?, días que suma),
  TTS, TTR (¿estimado?, de dónde sale), margen, estado, productos afectados (`Used_In_Products`) y
  necesidad mensual. También queda en el JSON de la auditoría.
- `test_detalle.csv`: columnas `Affected_Products`, `Countdown` (una línea por proveedor),
  `Min_Margin_Days` y `Countdown_Status` (el proveedor con menos margen).

## Observaciones en la entrega del test (anotadas, sin corregir)

- **N016** (huelga de 48 horas en Antwerp-Bruges): el LLM devuelve `recovery_days = 48`, es decir,
  confunde horas con días aunque el prompt da ese mismo ejemplo ("48 hours" -> 2). El margen sale
  −18 d ("rotura prevista") cuando debería ser holgado. Es un fallo de unidades del LLM; corregirlo
  ahora sería ajustar con una noticia del test.
- **N004** (warning letter a Kaveri): `Urgent = N`, pero la cuenta atrás da rotura prevista
  (−45 d) con un TTR por defecto de 90 días (estimado). Las dos señales miden cosas distintas; si
  la cuenta atrás debe influir en la urgencia es una decisión pendiente.
