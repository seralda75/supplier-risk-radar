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
riesgo, dónde, cuánto tiempo queda y qué hacer. Navegación lateral con cinco páginas (`st.navigation`:
solo se ejecuta la activa):

- **Centro de control**: banner de estado, 5 indicadores (alertas críticas, proveedores expuestos,
  medicamentos en riesgo, gasto anual expuesto en € y % del total, menor margen), la cola «Requiere tu
  decisión» (CRÍTICA = urgente; VIGILAR · RIESGO LATENTE = no urgente con margen negativo) ordenada por días
  de margen y, debajo, **Acciones en curso** (pedidos y recordatorios, con «Hecho»). A la derecha, el detalle
  de la alerta (qué pasa, cita con la duración resaltada, impacto, plan en pasos con responsable y plazo de
  `core/actions.py`, fiabilidad, noticia completa, Falsa alarma con motivo / Aprobar plan / Reabrir) y el mapa.
  Pulsar una tarjeta abre la **ventana de la alerta**: información (noticia, impacto, calendario de ese
  medicamento, plan) y decisión (aprobar, falsa alarma, **crear pedido** prellenado con la cantidad
  calculada, que queda como «pendiente de envío al ERP», y **crear recordatorio**), todo en SQLite
  (`core/feedback.py`, `core/tasks.py`). Debajo, a todo el ancho, el **calendario de roturas** (próximos 90
  días por medicamento) y el **treemap del gasto en riesgo** (lo que no tiene riesgo, agrupado en gris).
  Pulsar un proveedor en el mapa o en el treemap abre su ficha. Por defecto, las noticias de test; un
  selector discreto cambia a entrenamiento o validación.
- **Calendario**: qué medicamentos tienen stock suficiente, cuáles están en peligro y cuáles se quedan sin stock,
  y hasta qué día se puede esperar para pedir (`core/order_calendar.py`: fecha límite = hoy + días de stock −
  plazo del proveedor que se usaría). KPIs, calendario mensual o de 90 días con marcadores (último día para
  pedir, rotura prevista, recuperación, llegada del alternativo, pedidos y recordatorios) y semáforo de
  medicamentos. Pulsar un día abre su ventana con «Crear pedido» y «Crear recordatorio». Es una proyección
  desde hoy; respeta la falsa alarma y el modo demo.
- **Proveedores**: ranking de vulnerabilidad, % del gasto en proveedores únicos, concentración por país y por
  zona y alternativos que no llegan a tiempo. La ficha de proveedor (con su historial) se abre en una ventana
  desde el ranking o desde el buscador de la cabecera.
- **Simulador «¿Y si…?»** y **Transparencia** (métricas, cambios, límites, duraciones ancladas).

Las vistas de negocio no usan jerga: proveedores por nombre y ciudad, «días de margen» en lugar de TTS/TTR.
Inventario de elementos clicables, interacciones probadas con clic real y tiempos de respuesta: `docs/panel.md`.
La app solo lee `data/results/*.json` (incluidos en el repo): abre en segundos, sin llamar al LLM y sin
internet (fuentes IBM Plex y contorno del mapa servidos desde `static/`).

**Modo demo en directo** (interruptor «Modo demo» al pie del menú, o la URL con `?demo=1`): en el centro de
control aparece «Simular noticia entrante». Cada pulsación toma la siguiente noticia de un guion de validación
(`core/demo.py`) y la procesa con el pipeline real, paso a paso a la vista: noticia recibida → proveedores
candidatos → diagnóstico (IA local en directo, o con caché si se apaga «IA en directo»; sin Ollama, el
resultado precalculado) → cuenta atrás → alerta. La alerta entra resaltada («● NUEVA») y se actualizan KPIs,
calendario, mapa y treemap. Todo va a `data/demo.db`: no toca la entrega, los resultados ni `data/app.db`.

```powershell
.venv\Scripts\python scripts\reset_demo.py      # demo limpia (vacía data/demo.db)
.venv\Scripts\streamlit run app.py               # y abrir http://localhost:8501/?demo=1
```

«Reiniciar demo» hace lo mismo desde el panel. `scripts\reset_demo.py --panel` borra además las pruebas hechas
fuera del modo demo en `data/app.db` (decisiones, pedidos, recordatorios, comunicaciones), con copia previa y
sin tocar la auditoría del pipeline. Latencia: `scripts\latency_demo.py` (ver `docs/panel.md`).

**Agente de comunicaciones** (pestaña «✉ Comunicar» de la ventana de la alerta): correo al proveedor en inglés
y nota interna en español, editables. La IA local redacta el texto; las cifras de la nota las pone el código y
se comprueba que el texto de la IA no trae cifras ajenas a la alerta ni datos internos en el correo (si no,
plantilla). «Copiar» y «Marcar como enviado» (auditoría; la tarjeta muestra «✉ Comunicado»). No se envía nada.

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
core/feedback.py     respuestas de los compradores (aprobar plan / falsa alarma con motivo / reabrir) en SQLite
core/tasks.py        pedidos (pendientes de envío al ERP), recordatorios y comunicaciones marcadas como enviadas
core/comms.py        agente de comunicaciones: correo al proveedor y nota interna, con comprobación de cifras
core/demo.py         modo demo en directo: guion de noticias, pipeline en segundo plano, data/demo.db
core/order_calendar.py  fecha límite para pedir y estado (suficiente, en peligro, rotura) por material y medicamento
core/results.py      resultados guardados para el panel y métricas
core/countdown.py    cuenta atrás: TTS (inventario + alternativo) − TTR (recuperación)
core/actions.py      acción recomendada a partir de la cuenta atrás (déficit, alternativo a tiempo o no)
core/scenario.py     simulador «¿Y si…?»: escenario estructurado (LLM) + impacto calculado por código
core/pipeline.py     assess(noticia) -> veredicto + explicación + acción + auditoría
core/audit.py        auditoría en SQLite
core/data.py         carga de las noticias de los tres Excel
evaluate.py          métricas (python evaluate.py [--no-llm] [--split train])
app.py               panel Streamlit: estilo, menú lateral y st.navigation (docs/mockup_centro_control.html)
views/               una página por fichero (centro de control, calendario, proveedores, simulador, transparencia)
ui/                  contenido de cada página, ficha de proveedor, treemap, cachés, estilo y datos
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
