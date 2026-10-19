# Fase 5 · Simulador «¿Y si…?»

Pestaña **🧪 ¿Y si…?** del panel. El comprador escribe un escenario en lenguaje natural
(«¿y si se inunda Gujarat 3 semanas?») o elige uno de los ejemplos, revisa cómo se ha interpretado,
lo corrige si hace falta y calcula el impacto.

## Reparto de papeles

| Paso | Quién | Detalle |
|---|---|---|
| Texto → escenario | LLM (`qwen2.5:7b`, JSON schema + Pydantic) | Tipo de evento, países, regiones/ríos/rutas, ciudades/puertos, categorías, materiales y duración (valor + unidad, como en la noticia). No elige proveedores ni calcula nada |
| Salvaguardas | Código | Países en español → nombre de la hoja Suppliers; materiales copiados tal cual («viales») → nombre del catálogo; una categoría o un material solo se acepta si aparece en el texto del usuario (si no, se descarta y se muestra); un «material» que es una categoría («API») pasa a categorías |
| Revisión | Usuario | El escenario interpretado se muestra en un formulario editable. **No se calcula nada hasta pulsar «Calcular impacto»** |
| Proveedores afectados | Código | Mismo diccionario geográfico que los candidatos de las noticias (`matching._supplier_reasons`: ciudad, región, río, ruta, país). Si en un país hay coincidencias concretas, las que solo coinciden por ese país sobran (igual que en `find_candidates`). Después, filtro por material (si lo hay) o por categoría. Un evento de transporte no afecta a servicios |
| Impacto | Código | Cuenta atrás de la fase 3 (TTS − TTR) con la duración del escenario; sin duración, TTR por defecto del tipo de evento, marcado como estimado. Acciones de `core/actions.py` |

## Qué muestra

- Proveedores afectados con el motivo (p. ej. `region 'Gujarat'`, `categoría API`), TTS, TTR, margen, días de
  déficit y gasto anual.
- Materiales (principal y alternativo, cuál está afectado, peor margen) y productos (peor margen de sus
  materiales).
- Gasto anual expuesto y gasto de los proveedores con déficit previsto.
- Mapa con los proveedores afectados coloreados por margen y con tamaño según el gasto.
- Acciones recomendadas, del menor margen al mayor.
- Avisos: lugares sin proveedores de Helixa, proveedores de la zona fuera del escenario y restricciones
  descartadas por no estar en el texto.

## Sin Ollama

Los 7 ejemplos se interpretan una vez con `python scripts/build_scenarios.py` y se guardan en
`data/scenarios.json` (en el repo). Si Ollama no responde, el cuadro de texto se desactiva y el simulador
funciona con esos ejemplos; el formulario se puede seguir editando porque el cálculo no usa el LLM.

## Cómo se ajustó la interpretación

Los ejemplos del simulador no son datos del reto: son los del enunciado de la fase y los eventos típicos de
la sección 8.1 de CLAUDE.md. Ninguna noticia de validación ni de test se usó para diseñar el prompt ni las
salvaguardas. Problemas encontrados con los propios ejemplos y cómo se resolvieron:

| Problema | Solución |
|---|---|
| El LLM añadía el país de la región («Gujarat» → también India entera: S001, S034) | Regla del prompt + en código, las coincidencias solo por país sobran si hay otras más concretas |
| Tipo de evento erróneo (inundación → dificultades financieras, cierre de puerto → ciberataque) | Lista de correspondencias en el prompt |
| Con la lista cerrada de 30 materiales en el esquema, rellenaba materiales al azar y a veces se quedaba generando hasta agotar el tiempo | Materiales como texto libre copiado del escenario; el código los traduce al catálogo |
| Restricciones no pedidas («huelga de transportistas» → solo la categoría Logistics, que dejaba fuera a los fabricantes) | Una categoría o un material solo se acepta si alguna de sus palabras aparece en el texto |
| Países sin traducir («Países Bajos», «Taiwán») | Tabla de nombres de país en español en el código |

Resultado: los 7 ejemplos dan los proveedores esperados (test `test_los_ejemplos_precalculados_son_validos_y_afectan_a_alguien`).

## Límites

- El escenario describe lugares, categorías y materiales, no un proveedor concreto («¿y si quiebra Nordic
  Lipids?»): para eso está la ficha de proveedor.
- La duración por defecto es un orden de magnitud por tipo de evento (fase 3), no un dato medido.
- Logística y servicios no tienen inventario: su impacto es inmediato y todo el periodo cuenta como déficit,
  aunque exista un alternativo (la acción propone derivar al alternativo).
- Un modelo de 7B puede interpretar mal un texto ambiguo: por eso el escenario se muestra y se puede
  corregir antes de calcular.
