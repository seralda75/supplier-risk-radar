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
| 18/10/2026 | Fase 2 v4 · solo reglas + regla de exportación ⚠️ | entrenamiento (30) | 100 % | 100 % | 100 % | 93,3 % | 96,7 % | 93,3 % | 100 % |
| 18/10/2026 | Fase 2 v4 · solo reglas + regla de exportación ⚠️ | **validación (10)** | **100 %** | **90 %** | **100 %** | **90 %** | **97,5 %** | **80 %** | **100 %** |
| 18/10/2026 | Fase 2 v4 · v3 + regla de exportación ⚠️ | entrenamiento LOO (30) | 96,7 % | 100 % | 100 % | 96,7 % | 96,7 % | 96,7 % | 100 % |
| 18/10/2026 | Fase 2 v4 · v3 + regla de exportación ⚠️ | **validación (10)** | **100 %** | **90 %** | **100 %** | **90 %** | **96,7 %** | **80 %** | **100 %** |
| 18/10/2026 | Fase 2 v6 · v5 + corrección de `confidence` | entrenamiento LOO (30) | 96,7 % | 100 % | 100 % | 96,7 % | 96,7 % | 96,7 % | 100 % |
| 18/10/2026 | Fase 2 v6 · v5 + corrección de `confidence` | **validación (10)** | **100 %** | **90 %** | **100 %** | **90 %** | **96,7 %** | **80 %** | **100 %** |

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
  discrepancia (N041). Test: 13 de 20 noticias con consenso. Es una señal útil para decidir qué
  revisa una persona, aunque con tan pocos datos no es concluyente.
- Errores de urgencia que quedan en validación (anotados, no corregidos):
  - N041 (debía ser urgente): la palabra "temporary" rebaja la restricción a la exportación a
    gravedad 3 en los dos jueces y, como S002 y S006 tienen alternativo (dependencia ≤ 0,40), no
    llega al umbral; el README trata cualquier veto a la exportación como urgente. Además el LLM
    pierde S001 (Hyderabad), que las reglas sí incluyen.
  - N044 (no debía ser urgente): las reglas dan gravedad 4 al racionamiento eléctrico ("two weeks")
    y el LLM 2; la media redondeada hacia arriba (3) más la dependencia alta de S003, proveedor único
    (0,90), lo convierten en urgente, cuando la etiqueta considera limitado un recorte del 20 %.

Notas de la fase 2 v4 (⚠️ cambio motivado por validación y respaldado por el README):
- **Qué cambia:** una restricción o veto a la exportación que afecta a proveedores es urgente
  siempre, aunque sea temporal y aunque el proveedor tenga alternativo (`urgency.is_urgent()`, en
  los dos modos). El README del reto pone "an export ban" como ejemplo explícito de urgente.
- **Por qué se marca:** la regla sale del README, pero se añadió después de ver el error N041 de
  validación. La validación de la v4 ya no es independiente para este caso.
- En entrenamiento no hay ninguna restricción a la exportación: las métricas no cambian (reglas y LLM).
- Validación: N041 ya sale urgente (recall de urgentes 50 % → 100 %), pero sigue sin ser perfecta
  por los IDs: el LLM pierde S001 (Hyderabad) y las reglas añaden S007 (China). Noticias perfectas: 80 %.
- La entrega del test no cambia (ninguna noticia del test es una restricción a la exportación); se
  regenera igualmente con la v4.
- **Límite conocido, sin corregir: N044** (racionamiento eléctrico del 20 % durante dos semanas en
  Zhejiang). Sale urgente porque la gravedad combinada (3) coincide con un proveedor único (S003,
  dependencia 0,90), mientras que la etiqueta lo considera un efecto limitado. Arreglarlo exigiría
  una regla hecha a medida para ese titular; se deja como falsa alarma, el error menos costoso
  según la prioridad del reto (recall de urgentes).

Notas de la fase 2 v5 · política de desempate entre reglas y LLM:
- **Cómo se decidió:** solo con el entrenamiento (leave-one-out) y la validación; el test no se usó.
  En cada campo en el que los dos jueces discrepan, se cuenta quién coincide con la etiqueta:

  | Campo | Discrepancias (30 entrenamiento + 10 validación) | Acierta el LLM | Aciertan las reglas | Ninguno |
  |---|---|---|---|---|
  | Is_Risk | 1 (N037) | 0 | 1 | 0 |
  | Urgent | 0 | — | — | — |
  | Affected_Supplier_IDs | 3 (N011, N037, N041) | 1 (N011) | 0 | 2 (N037, N041) |

- **Política:** manda el LLM en los tres campos (`TIEBREAK` en `core/pipeline.py`). Ninguna diferencia
  es clara: 1 a 0 no es evidencia, y además las reglas se diseñaron con el entrenamiento, así que su
  acierto allí es optimista. El criterio acordado era mantener el LLM si la diferencia no es clara.
- Solo un riesgo puede ser urgente: si el desempate dejara Is_Risk = N, Urgent pasa a N.
- La política es configurable ("llm" o "reglas" por campo): cuando haya más histórico (por ejemplo,
  las respuestas de "falsa alarma" de los compradores) se puede volver a medir y cambiar.
- Efecto: ninguno en las métricas ni en la entrega (ya decidía el LLM). `test_detalle.csv` añade la
  columna `Tiebreak` con quién decide cada campo en discrepancia (7 noticias del test).

Límite conocido · el LLM marca como riesgo noticias que solo coinciden por ubicación:
- **Qué pasa:** cuando una noticia menciona el lugar de un proveedor pero no describe ninguna
  interrupción del suministro, el LLM tiende a marcarla como riesgo. Se ve en las discrepancias
  del test (observación, no se ha usado para ajustar nada): N021 (ola de frío prevista en el Medio
  Oeste → S017), N036 (plan para automatizar el puerto de Singapur → S032) y N049 (ampliación del
  metro de Hyderabad → S001). En las tres, las reglas dicen "sin riesgo".
- **Por qué no se corrige ahora:** no aparece en el entrenamiento ni en la validación (el LLM
  acierta N013, N028, N042, N045 y N058, que son de este tipo), así que cualquier regla nueva
  estaría hecha a medida para el test.
- **Señales que ya lo detectan:** las tres noticias no tienen consenso con las reglas y, desde la
  v7, salen con revisión humana (`Review_Reason = sin_consenso`).
  ~~En las tres el LLM da una confianza muy baja (0,03-0,04) y salen con revisión humana.~~ Corregido
  en la v6: esa confianza baja era un fallo del campo `confidence`, no una señal real.
- **Mitigación en producción:** la marca de revisión humana (una persona confirma antes de alertar)
  y la respuesta de los compradores ("falsa alarma" en el bot), que se guarda y sirve para ajustar
  umbrales y añadir ejemplos nuevos al few-shot.

Notas de la fase 2 v6 · corrección de un fallo detectado al revisar las discrepancias:
- **Síntoma:** en el test, N021, N036 y N049 salían con is_risk = true y confianza 0,03-0,04, algo
  incoherente. En entrenamiento y validación pasaba lo mismo en riesgos BIEN clasificados (N037,
  N053, N041, N044), mientras que las noticias sin riesgo tenían confianza 1,0: no era el error lo
  que bajaba la confianza.
- **Causa (comprobada con la salida cruda de Ollama, sin caché ni validador):** el modelo NO
  interpretaba `confidence` como probabilidad de riesgo, sino que mezclaba escalas: unas veces un
  porcentaje (80) y otras una nota parecida a la de 1 a 5 de `severity` (3 o 4). Nuestro validador
  dividía entre 100 todo valor entre 1 y 100, así que un 4 se convertía en 0,04. El campo estaba
  mal definido (descripción en español, ambigua, y sin mención en el prompt de sistema).
- **Corrección:** (1) descripción precisa del campo en el esquema, en inglés como el prompt;
  (2) regla 11 del prompt: un decimal de 0,0 a 1,0 con la seguridad en la propia respuesta, ni
  probabilidad de riesgo ni nota de 1 a 5; (3) el validador solo convierte porcentajes claros
  (> 5) y rechaza los valores ambiguos entre 1 y 5, de modo que `extract()` reintenta. No se añade un
  campo `risk_probability`: el problema era de escala, no de significado.
- **Iteración (solo con el entrenamiento):** una primera redacción de la regla 11 con ejemplos
  ("0.9 = very sure… a clearly irrelevant article gets is_risk = false") empeoraba el
  entrenamiento (N025, cambio de CEO, pasaba a "sin riesgo": 96,7 % → 93,3 % en Is_Risk). Se
  descartó por una redacción neutra y sin anclas, que deja entrenamiento y validación igual que la v5.
- **Resultado:** las métricas no cambian y la entrega del test se regenera con las mismas 20 respuestas.
- **Hallazgo:** con la escala corregida, la confianza del LLM es casi constante (0,95 en 31 de 36
  noticias con candidatos de entrenamiento y validación, 1,0 en el resto), también en el único
  error de Is_Risk (N034). La confianza que el modelo declara sobre sí mismo **no separa aciertos de
  errores**, así que `Needs_Review` (confianza < 0,75) ya no se activa en ninguna noticia del test.
  La señal útil para la revisión humana es la falta de consenso entre reglas y LLM (acierto del
  100 % con consenso frente a 0-50 % sin consenso).

Notas de la fase 2 v7 · revisión humana basada en el consenso:
- **La confianza declarada por el LLM no discrimina aciertos de errores.** Tras corregir su escala
  (v6) es casi constante: en entrenamiento, 0,95 en 21 noticias y 1,0 en 5 (las otras 4 no tienen
  candidatos y no pasan por el LLM); en validación, 0,95 en las 10. Los errores tienen la misma
  confianza que los aciertos: N037 (entrenamiento), N041 y N044 (validación) tienen 0,95, igual que
  la media de los aciertos (0,95-0,96). Con el umbral de 0,75, la marca antigua no capturaba
  **ningún** error.
- **El consenso entre reglas y LLM sí es una señal de incertidumbre:**

  | Conjunto | Consenso | Perfecta con consenso | Perfecta sin consenso | Marcadas para revisión | Errores capturados |
  |---|---|---|---|---|---|
  | Entrenamiento LOO (30) | 93,3 % | 100 % | 50 % (1 de 2) | 6,7 % (2) | 100 % (1 de 1: N037) |
  | Validación (10) | 90 % | 88,9 % | 0 % (0 de 1) | 10 % (1) | 50 % (1 de 2: N041; N044 no) |

- **Regla:** `Needs_Review` = (riesgo con confianza < 0,75) **o** (reglas y LLM discrepan en algún
  campo). El motivo se guarda en `Review_Reason` (`confianza_baja`, `sin_consenso` o ambos) en
  `test_detalle.csv` y en la columna `review_reason` de la auditoría.
- **No cambia ninguna respuesta Y/N:** solo decide qué noticias revisa una persona. En el test se
  marcan 7 de 20 (todas por `sin_consenso`): N003, N009, N021, N036, N043, N049 y N055.
- **Límite:** cuando los dos jueces se equivocan igual (N044), la marca no salta. Con 40 noticias
  etiquetadas, los porcentajes de esta tabla son orientativos.
