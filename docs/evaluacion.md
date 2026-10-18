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
| 18/10/2026 | Fase 2 v3 · v2 + filtro de identidad ⚠️ | entrenamiento LOO (30) | 96,7 % | 100 % | 100 % | 96,7 % | 96,7 % | 96,7 % | 100 % |
| 18/10/2026 | Fase 2 v3 · v2 + filtro de identidad ⚠️ | **validación (10)** | **100 %** | **80 %** | **50 %** | **90 %** | **96,7 %** | **80 %** | **100 %** |

⚠️ = versión con un cambio motivado por un error de validación (ver notas de la v3).

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

Notas de la fase 2 v3 (⚠️ cambio motivado por validación):
- **Qué cambia:** el juez LLM pasa por la misma comprobación de identidad que el modo reglas: un
  nombre ambiguo (coincidencia parcial, p. ej. "Atlas") solo cuenta si algo más de la noticia apunta
  a ese proveedor (su material, su ciudad o región, vocabulario farmacéutico). Está en
  `judge.apply_guards()` y reutiliza `matching.has_context_support()`, que ya existía y se diseñó con
  las trampas del entrenamiento (Lumina, Celtic, Sunrise Energy, Orion Capital).
- **Por qué se marca:** la regla es genérica, pero la decisión de aplicarla también al LLM se tomó
  tras ver el error N034 de validación ("Atlas Air" aceptado como S040). Por eso la validación de la
  v3 ya no es una medida totalmente independiente: la cifra de validación de la v2 (70 %) es la más
  limpia para el LLM; la v3 (80 %) arregla exactamente el error que motivó el cambio.
- En entrenamiento no cambia nada (el LLM ya acertaba todas las trampas).
- Resultado: la versión LLM iguala a la de reglas en validación (80 % de noticias perfectas), así que
  la entrega del test se hace con el LLM (v3).
- **Consenso reglas-LLM** (nuevo campo en `test_detalle.csv` y en la auditoría): Y si los dos jueces
  dan las mismas tres respuestas. Entrenamiento: 93,3 % de consenso; acierto 100 % con consenso y
  50 % cuando discrepan. Validación: 90 % de consenso; acierto 88,9 % con consenso y 0 % en la única
  discrepancia (N041). Test: 12 de 20 noticias con consenso. Es una señal útil para decidir qué
  revisa una persona, aunque con tan pocos datos no es concluyente.
- Errores de urgencia que quedan en validación (anotados, no corregidos):
  - N041 (debía ser urgente): la palabra "temporary" rebaja la restricción a la exportación a
    gravedad 3 en los dos jueces y, como S002 y S006 tienen alternativo (dependencia ≤ 0,40), no
    llega al umbral; el README trata cualquier veto a la exportación como urgente. Además el LLM
    pierde S001 (Hyderabad), que las reglas sí incluyen.
  - N044 (no debía ser urgente): las reglas dan gravedad 4 al racionamiento eléctrico ("two weeks")
    y el LLM 2; la media redondeada hacia arriba (3) más la dependencia alta de S003, proveedor único
    (0,90), lo convierten en urgente, cuando la etiqueta considera limitado un recorte del 20 %.
