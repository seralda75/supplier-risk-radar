# Supplier Risk Radar · Helixa Pharmaceuticals

Monitor de noticias con IA local (Ollama) que detecta riesgos de suministro, identifica los
proveedores afectados (por nombre o por ubicación) y decide si hay que alertar ya a compras.
Contexto completo del reto y de la arquitectura en `CLAUDE.md`.

## Puesta en marcha (Windows, Python 3.12)
```powershell
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
ollama pull qwen2.5:7b; ollama pull nomic-embed-text
.venv\Scripts\python scripts\check_env.py
```

## Estructura
```
data/raw/            Excel originales del reto
core/config.py       rutas, modelos y parámetros
core/llm.py          cliente de Ollama: chat, extract (JSON schema + Pydantic + caché), embed
core/rag.py          ejemplos parecidos en ChromaDB
core/schemas.py      NewsAssessment (salida del juez) y taxonomía de eventos
core/suppliers.py    fichas de proveedores + diccionario geográfico
core/matching.py     candidatos por nombre, ubicación, ruta, material y categoría (RapidFuzz)
core/rules.py        modo solo reglas: tipo de evento, gravedad y proveedores afectados
core/urgency.py      dependencia del proveedor y decisión de urgencia
core/judge.py        juez LLM: few-shot del entrenamiento (Chroma) + JSON schema + salvaguardas
core/countdown.py    cuenta atrás: TTS (inventario + alternativo) − TTR (recuperación)
core/pipeline.py     assess(noticia) -> veredicto + explicación + acción + auditoría
core/audit.py        auditoría en SQLite
core/data.py         carga de las noticias de los tres Excel
evaluate.py          métricas (python evaluate.py [--no-llm] [--split train])
fill_test.py         rellena outputs/Supplier_Risk_3_Test_respuestas.xlsx y valida el formato
deliverables/        entrega final del test (copia versionada de outputs/) + detalle con consenso
tests/               pytest con casos del entrenamiento
docs/evaluacion.md   historial de métricas
docs/fase3_cuenta_atras.md supuestos de la cuenta atrás
scripts/check_env.py comprobación del entorno
scripts/bench_models.py comparación de modelos (ver docs/fase0_modelos.md)
```
