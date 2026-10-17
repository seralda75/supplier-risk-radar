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
core/schemas.py      NewsAssessment (salida del juez)
scripts/check_env.py comprobación del entorno
scripts/bench_models.py comparación de modelos (ver docs/fase0_modelos.md)
```
