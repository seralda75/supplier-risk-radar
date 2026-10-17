# Historial de evaluación

Reglas del juego: la validación **solo se mide**. Reglas, diccionario geográfico, tipos de evento y
prompts se diseñan con el entrenamiento (30 noticias), el README del reto y conocimiento general.
Los errores de validación se anotan, pero no se corrigen con reglas hechas a medida.

| Fecha | Versión | Conjunto | Is_Risk | Urgent | Recall urgentes | IDs exactos | Jaccard IDs | Noticia perfecta | Recall candidatos |
|---|---|---|---|---|---|---|---|---|---|
| 17/10/2026 | Fase 1 · solo reglas | entrenamiento (30) | 100 % | 100 % | 100 % | 93,3 % | 96,7 % | 93,3 % | 100 % |
| 17/10/2026 | Fase 1 · solo reglas | **validación (10)** | **100 %** | **80 %** | **50 %** | **90 %** | **97,5 %** | **80 %** | **100 %** |

Notas de la fase 1 (solo reglas):
- En entrenamiento el acierto es casi perfecto porque las reglas se diseñaron con esos datos: la cifra honesta es la de validación.
- Errores en validación: una restricción temporal a la exportación queda con gravedad 3 (la palabra
  "temporary" la rebaja) y no sale urgente; un racionamiento eléctrico de dos semanas sale urgente.
  Matizar la intensidad de un evento es justo lo que debe aportar el juez LLM (fase 2).
