# Historial de evaluación

Reglas del juego: la validación **solo se mide**. Reglas, diccionario geográfico, tipos de evento y
prompts se diseñan con el entrenamiento (30 noticias), el README del reto y conocimiento general.
Los errores de validación se anotan, pero no se corrigen con reglas hechas a medida.

| Fecha | Versión | Conjunto | Is_Risk | Urgent | Recall urgentes | IDs exactos | Jaccard IDs | Noticia perfecta | Recall candidatos |
|---|---|---|---|---|---|---|---|---|---|
| 17/10/2026 | Fase 1 · solo reglas | entrenamiento (30) | 100 % | 100 % | 100 % | 93,3 % | 96,7 % | 93,3 % | 100 % |
| 17/10/2026 | Fase 1 · solo reglas | **validación (10)** | **100 %** | **80 %** | **50 %** | **90 %** | **97,5 %** | **80 %** | **100 %** |
| 18/10/2026 | Fase 2 v1 · LLM qwen2.5:7b | entrenamiento LOO (30) | 90 % | 90 % | 40 % | 93,3 % | 93,3 % | 76,7 % | 100 % |
| 18/10/2026 | Fase 2 v2 · LLM + gravedad combinada | entrenamiento LOO (30) | 96,7 % | 100 % | 100 % | 96,7 % | 96,7 % | 96,7 % | 100 % |
| 18/10/2026 | Fase 2 v2 · LLM + gravedad combinada | **validación (10)** | **90 %** | **80 %** | **50 %** | **80 %** | **86,7 %** | **70 %** | **100 %** |

Notas de la fase 1 (solo reglas):
- En entrenamiento el acierto es casi perfecto porque las reglas se diseñaron con esos datos: la cifra honesta es la de validación.
- Errores en validación: una restricción temporal a la exportación queda con gravedad 3 (la palabra
  "temporary" la rebaja) y no sale urgente; un racionamiento eléctrico de dos semanas sale urgente.
  Matizar la intensidad de un evento es justo lo que debe aportar el juez LLM (fase 2).

Notas de la fase 2 (LLM):
- v1 → v2, cambios hechos SOLO con errores de entrenamiento: (1) el LLM comprime la escala de
  gravedad (una retirada de lotes o una suspensión de licencia le parecen "no inmediatas") → la
  gravedad final es la media redondeada hacia arriba de LLM y reglas, y la inmediatez basta con que
  la vea uno; (2) el prompt explicita que adquisición, cambio de CEO o rebaja de rating son riesgo
  (convención del entrenamiento); (3) una noticia positiva conserva el ID del proveedor nombrado.
- "LOO" = leave-one-out: cada noticia de entrenamiento se evalúa sin poder usarse a sí misma como ejemplo.
- Errores en validación (v2): N034 "Atlas Air" (el LLM acepta el nombre trampa como S040; el modo
  reglas lo descartaba al exigir contexto), N041 (falta S001 y no sale urgente), N044 (racionamiento
  eléctrico marcado como urgente; también fallaba en reglas).
- Con 10 noticias, cada noticia vale 10 puntos: reglas (80 %) y LLM (70 %) se separan por UNA noticia.
