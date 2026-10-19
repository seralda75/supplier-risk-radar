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

## Panel (Streamlit)
```powershell
.venv\Scripts\python scripts\build_results.py     # guarda los resultados de los 3 conjuntos (usa la caché del LLM)
.venv\Scripts\streamlit run app.py                 # http://localhost:8501
```
Diseño de `docs/mockup_centro_control.html`, pensado para el director de compras: en 5 segundos, si hay
riesgo, dónde, cuánto tiempo queda y qué hacer. Navegación lateral con cuatro vistas:

- **Centro de control**: banner de estado, 5 indicadores (alertas críticas, proveedores expuestos,
  medicamentos en riesgo, gasto anual expuesto en € y % del total, menor margen), la cola «Requiere tu
  decisión» (CRÍTICA = urgente; VIGILAR · RIESGO LATENTE = no urgente con margen negativo) ordenada por días
  de margen, el detalle de la alerta (qué pasa, cita con la duración resaltada, impacto, plan en pasos con
  responsable y plazo de `core/actions.py`, fiabilidad, botones Falsa alarma / Aprobar plan guardados en
  SQLite), «¿Cuánto aguantamos?» y el mapa. Por defecto, las noticias de test; un selector discreto cambia
  a entrenamiento o validación.
- **Proveedores**: ranking de vulnerabilidad, % del gasto en proveedores únicos, concentración por país y por
  zona, alternativos que no llegan a tiempo y ficha por proveedor con su historial.
- **Simulador «¿Y si…?»** y **Transparencia** (métricas, cambios, límites, duraciones ancladas).

Las vistas de negocio no usan jerga: proveedores por nombre y ciudad, «días de margen» en lugar de TTS/TTR.
La app solo lee `data/results/*.json` (incluidos en el repo): abre en segundos, sin llamar al LLM y sin
internet (fuentes IBM Plex y contorno del mapa servidos desde `static/`).

**Simulador «¿Y si…?»** (fase 5): el LLM convierte la pregunta en un escenario estructurado que el usuario
revisa; el código calcula proveedores, materiales, productos, margen, gasto expuesto y acciones. Sin Ollama
funciona con los ejemplos precalculados (`python scripts/build_scenarios.py` los regenera). Ver
`docs/fase5_simulador.md`.

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
core/geo.py          coordenadas de las 40 ciudades (mapa)
core/feedback.py     respuestas de los compradores (confirmar / falsa alarma) en SQLite
core/results.py      resultados guardados para el panel y métricas
core/countdown.py    cuenta atrás: TTS (inventario + alternativo) − TTR (recuperación)
core/actions.py      acción recomendada a partir de la cuenta atrás (déficit, alternativo a tiempo o no)
core/scenario.py     simulador «¿Y si…?»: escenario estructurado (LLM) + impacto calculado por código
core/pipeline.py     assess(noticia) -> veredicto + explicación + acción + auditoría
core/audit.py        auditoría en SQLite
core/data.py         carga de las noticias de los tres Excel
evaluate.py          métricas (python evaluate.py [--no-llm] [--split train])
app.py               panel Streamlit: navegación y vistas (diseño de docs/mockup_centro_control.html)
ui/                  vistas del panel (control, proveedores, simulador, transparencia), estilo y datos
core/labels.py       nombres en español para las vistas de negocio
static/              fuentes IBM Plex (licencia OFL) y contorno del mapa: el panel funciona sin internet
scripts/build_results.py  genera data/results/{train,validation,test}.json
scripts/build_scenarios.py interpreta los ejemplos del simulador -> data/scenarios.json
fill_test.py         rellena outputs/Supplier_Risk_3_Test_respuestas.xlsx y valida el formato
deliverables/        entrega final del test (copia versionada de outputs/) + detalle con consenso
tests/               pytest con casos del entrenamiento
docs/evaluacion.md   historial de métricas
docs/fase3_cuenta_atras.md supuestos de la cuenta atrás
docs/fase5_simulador.md    simulador «¿Y si…?»
scripts/check_env.py comprobación del entorno
scripts/bench_models.py comparación de modelos (ver docs/fase0_modelos.md)
```
