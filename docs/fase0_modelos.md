# Fase 0 · Elección del modelo del juez

Medido con `scripts/bench_models.py` (17/10/2026) sobre 8 noticias **de entrenamiento**
(nombres trampa, riesgo por ubicación, noticia positiva, urgente y no urgente), con un prompt
del tamaño del real (fichas de candidatos + 3 ejemplos, ~580 tokens), temperatura 0, `num_ctx` 4096.
Máquina: RTX 3050 Ti Laptop (4 GB VRAM), Ollama 0.40.5.

| Modelo | Latencia media | Tokens/s | JSON válido al 1.er intento | Is_Risk | IDs exactos | Memoria |
|---|---|---|---|---|---|---|
| **qwen2.5:7b** | 20,6 s | 6,1 | 100 % | **8/8** | **7/8** | 45 % en GPU |
| qwen2.5:3b | 6,4 s | 23,3 | 100 % | 5/8 | 4/8 | 100 % en GPU |
| llama3.2:3b | 5,6 s | 29,6 | 100 % | 8/8 | 6/8 | 80 % en GPU |

**Decisión:** `qwen2.5:7b` como juez (`LLM_MODEL`); `llama3.2:3b` como reserva rápida (`LLM_FAST_MODEL`).
llama3.2:3b llegó a devolver un ID que no estaba entre los candidatos (S019) → el juez filtra
siempre los IDs contra la lista de candidatos.

**Lecciones que cambiaron el código:**
1. Los campos con valor por defecto salen como opcionales en el JSON schema y los modelos se los
   saltan (`affected_ids`, `recovery_days`): en `NewsAssessment` todos los campos son obligatorios.
2. Ollama impone la estructura del JSON, no los rangos: algunos modelos devuelven `confidence: 80`.
   Se normaliza a 0,8 en el validador.
3. `num_ctx` 8192 dejaba llama3.2:3b al 67 % en GPU y con 65 s de carga; 4096 basta y `llm.extract`
   avisa si el prompt se acerca al límite (Ollama trunca en silencio).
4. Con ~21 s por noticia, la caché en disco de `llm.extract` hace que re-evaluar tras cambiar
   reglas sea instantáneo.
