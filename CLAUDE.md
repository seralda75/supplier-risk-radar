# CONTEXTO DEL PROYECTO · Supplier Risk Radar (Hackathon Accenture GenAI Mavericks)

> **Para Claude:** este documento te da todo el contexto necesario para construir el MVP.
> Léelo entero antes de escribir código. Junto a él se adjuntan los Excel originales del reto.
> Trabaja en español. Explica las decisiones técnicas de forma breve: el proyecto se presenta a un jurado de Accenture
> como si fuera una solución vendible a una empresa farmacéutica.

---

## 1. Situación

- **Evento:** GenAI Mavericks (Accenture Madrid). Sesiones presenciales el 16 y el 23 de octubre de 2026. El día 23 se presenta el pitch con demo.
- **Equipo:** estudiantes de Ingeniería Informática (UFV).
- **Reto asignado:** *Challenge 4: Supplier Risk Radar, AI News Monitoring.*
- **Stack recomendado por Accenture** (no es obligatorio): Streamlit/Gradio · SQLite/PostgreSQL/JSON/CSV/FAISS/Chroma · Ollama OCR/docTR · Pydantic · LangChain/CrewAI/n8n · Ollama + Llama · Colab/Jupyter/GitHub/Python.

## 2. El reto

Las farmacéuticas dependen de cientos de proveedores (ingredientes, envases, logística). Un incendio, una huelga, un huracán, una
restricción a la exportación, una acción regulatoria o la quiebra de un proveedor pueden cortar el suministro. Estos eventos suelen aparecer antes en las noticias, pero nadie
puede leer miles de artículos al día.

**La solución debe, para cada noticia:**
1. `Is_Risk`: decidir si es un riesgo para el suministro (Y/N).
2. `Affected_Supplier_IDs`: identificar los proveedores afectados, **por nombre o por ubicación**.
3. `Urgent`: decidir si hay que alertar ya al equipo de compras (Y/N), según **la gravedad del evento × la dependencia del proveedor**
   (proveedor único, criticidad, días de inventario). Solo un riesgo puede ser urgente.

**Definición oficial de urgencia (README del reto):** `Urgent = Y` cuando el evento puede parar o retrasar seriamente
el suministro pronto (por ejemplo, un incendio en planta, un regulador que bloquea envíos, un desastre natural que cierra fábricas, un veto a la exportación o un proveedor
al borde de la quiebra). `N` para efectos menores, cortos o lentos que pueden esperar al informe semanal.

## 3. Datos (empresa ficticia: Helixa Pharmaceuticals)

| Fichero | Contenido | Uso |
|---|---|---|
| `Supplier_Risk_1_Training.xlsx` | Hojas `README`, `Suppliers` (40), `Materials` (20), `News` (30 noticias etiquetadas) | Construir y ajustar el sistema (few-shot, reglas, umbrales) |
| `Supplier_Risk_2_Validation.xlsx` | Hoja `News_Validation` (10 etiquetadas) | **Solo medir.** No entrenar con ellas. Llegaron dos copias idénticas: usar una |
| `Supplier_Risk_3_Test.xlsx` | Hoja `News_Test` (20 sin etiquetar) | Rellenar las respuestas y entregar. **Los moderadores puntúan este fichero** |

**Columnas de las noticias:** `News_ID, Published_Date, Source, Headline, Summary, Is_Risk, Urgent, Affected_Supplier_IDs, Event_Type, Explanation`
(en el test solo están hasta `Affected_Supplier_IDs`, que van vacías).

**Formato exacto de la entrega:**
- `Is_Risk` y `Urgent` toman los valores `Y` o `N`. Si `Is_Risk = N`, entonces `Urgent = N`.
- `Affected_Supplier_IDs` contiene IDs separados por `"; "` (por ejemplo `S003; S007`), o se deja vacío si no hay ninguno.

### Observaciones clave del conjunto de entrenamiento (el sistema DEBE gestionarlas)
1. **Nombres trampa:** "'Lumina' tops the box office" es una película, no Lumina Glassworks. "Celtic beat Rangers" es fútbol, no Celtic BioLogics.
   "Sunrise Energy" no es Sunrise BioChem. "Orion Capital" no es Orion Synthesis. → Hay que **verificar la identidad**, no solo comparar el texto.
2. **Riesgos por ubicación sin nombrar al proveedor:** "Inundaciones en Gujarat" → S002, S006, S014 (Ahmedabad y Vadodara). "Bajo nivel del Rin" → S039 (Colonia)
   y S009 (Ludwigshafen). "Huracán en Puerto Rico" → S025. "Terremoto en el sur de Taiwán" → S013 (Kaohsiung). "Huelga en los puertos de Rotterdam" → S030 y S038.
3. **La categoría también importa:** "Huelga nacional de camioneros en España" → S018 y S011 (bienes físicos), pero **no** S035 (software de serialización, Madrid).
   "Rutas marítimas desviadas por el mar Rojo" → S032 (agencia marítima).
4. **Las noticias positivas sobre un proveedor llevan su ID aunque `Is_Risk = N`.** Por ejemplo, "Sunrise BioChem completes US inspection" → `Is_Risk = N` y `IDs = S001`.
   Lo mismo ocurre con S008 y S037. Hay que replicar este patrón (pendiente de confirmar con los mentores).
5. **La urgencia depende del evento y de la dependencia:** el terremoto en Taiwán afecta a S013, que no es proveedor único → riesgo pero no urgente. Una rebaja de rating (S011) → no urgente;
   en cambio, una duda sobre la continuidad de la empresa con un impago (S012, proveedor único) → urgente. Un cambio de CEO (S030) o una adquisición por un competidor (S020) → riesgo no urgente.
6. **Distribución:** 16 noticias sin riesgo y 14 con riesgo, de las cuales 5 son urgentes. Con tan pocos datos **no tiene sentido entrenar un clasificador**: se usa un LLM con ejemplos (few-shot) y reglas.

## 4. Arquitectura acordada (MVP)

```
Noticia → [1] Carga → [2] Fichas de proveedores + diccionario geográfico → [3] Candidatos (RapidFuzz + ubicación + categoría)
       → [4] Ejemplos parecidos del entrenamiento (Chroma) → [5] Juez LLM (Ollama, salida Pydantic)
       → [6] Urgencia = evento (LLM) × dependencia (reglas) → [7] Explicación + acción recomendada
       → [8] SQLite (auditoría) → [9] Alertas (n8n → Teams/correo) → [10] Panel Streamlit
       + evaluate.py (validación) + fill_test.py (rellena el Excel de test)
```

| Paso | Herramienta | Detalle | Justificación (para el pitch) |
|---|---|---|---|
| 1 Carga | pandas + openpyxl | Leer los Excel. En producción: API de noticias o Reuters vía n8n | Lee Excel de forma nativa |
| 2 Fichas | pandas | Unir Suppliers y Materials: material, productos, proveedor único, alternativo, criticidad, inventario. Añadir un **diccionario geográfico** manual: ciudad → región/estado, río, puerto, zona (Gujarat, Rin, sur de Taiwán, Puerto Rico…) | El LLM razona con datos reales de negocio |
| 3 Candidatos | RapidFuzz + reglas | Coincidencia aproximada con el nombre normalizado (sin "Ltd", "GmbH", "SpA"…), coincidencia de ciudad/región/país y filtro por categoría (la logística afecta a bienes físicos, no a servicios). **Objetivo: no perder ningún proveedor (recall alto)** | Determinista, gratis y **escalable a cientos de proveedores** |
| 4 Ejemplos | ChromaDB + `nomic-embed-text` | Recuperar las 3–5 noticias de entrenamiento más parecidas **con su `Explanation`** | El README pide copiar ese razonamiento |
| 5 Juez | Ollama `qwen2.5:7b`, temperatura 0, `format` = JSON schema de Pydantic | Confirma o descarta candidatos (nombres trampa) y clasifica el evento | LLM local: confidencialidad en el sector farmacéutico, sin coste por consulta, reproducible |
| 6 Urgencia | Python | El LLM devuelve `severity` (1–5) y `stops_supply_soon`. El código calcula la dependencia (proveedor único, criticidad, inventario, alternativo). Umbrales ajustados con el entrenamiento | Explicable y ajustable por el cliente |
| 7 Acción | Python + LLM | Texto con el estilo de `Explanation` y una acción **calculada a partir de los datos** (activar el alternativo X, quedan N días de inventario de Y, productos afectados) | Valor de negocio, no solo un aviso |
| 8 Auditoría | SQLite | Noticia, decisión, evidencia, confianza, fecha | Trazabilidad exigida en el sector farmacéutico |
| 9 Alertas | n8n | Solo las urgentes en el momento; el resto en un resumen semanal | Evita saturar al equipo; usa canales que ya conocen |
| 10 Panel | Streamlit (+ mapa con Plotly/pydeck) | Bandeja de alertas ordenada por riesgo, mapa de proveedores expuestos, ficha de proveedor, pestaña de métricas | Demo completa en horas, toda en Python |

### Esquema Pydantic orientativo
```python
class NewsAssessment(BaseModel):
    is_risk: bool
    event_type: Literal["fire_plant_incident","natural_disaster","labour_strike","logistics_disruption",
                        "regulatory_action","quality_recall","export_restriction","financial_distress",
                        "acquisition","leadership_change","positive_news","not_relevant"]
    affected_ids: list[str]          # validador: deben estar entre los candidatos/IDs existentes (no se pueden inventar)
    severity: int = Field(ge=1, le=5)
    stops_supply_soon: bool
    evidence: str                    # frase de la noticia que lo justifica
    confidence: float = Field(ge=0, le=1)
```

### Evaluación (imprescindible para el pitch)
- `evaluate.py` sobre la validación: porcentaje de acierto en `Is_Risk` y en `Urgent`, coincidencia exacta y Jaccard de los IDs, y una tabla con los errores.
- Se prioriza el **recall de las urgentes**: no detectar un incendio es peor que dar una falsa alarma.
- `fill_test.py`: genera `Supplier_Risk_3_Test_respuestas.xlsx` con el formato exacto, conservando el resto del fichero.

## 5. Entorno y código existente

- **Proyecto:** `C:\Mavericks\supplierRiskRadar` (repo nuevo). Excel originales en `data/raw/`.
- **Máquina:** Windows, Python **3.12** (no usar 3.13), GPU NVIDIA. Crear un `.venv` nuevo
  (`py -3.12 -m venv .venv`) e instalar las dependencias necesarias.
- **Ollama instalado** con `qwen2.5:7b` y `nomic-embed-text` (también `llama3.2-vision`, que no hace falta: las noticias son texto).
- **Kit genérico** en `C:\Mavericks\hackathon-starter\hackathon-starter` (repo `github.com/seralda75/mavericks-kit`).
  Copiar de ahí y adaptar estos módulos (no reescribirlos):
  - `core/config.py`: rutas y modelos (`LLM_MODEL`, `EMBED_MODEL`, `OLLAMA_URL`, `CONFIDENCE_THRESHOLD`).
  - `core/llm.py`: `is_up()`, `chat()`, `extract(text, PydanticModel, instructions)` (JSON schema nativo de Ollama + validación + reintentos) y `embed()`.
  - `core/rag.py`: indexado y búsqueda en ChromaDB persistente. Ojo: **los nombres de colección deben tener al menos 3 caracteres**.
  - `core/agent.py`: patrón de reglas + LLM + revisión humana + auditoría en SQLite (estaba pensado para facturas; usarlo como referencia).
  - `scripts/check_env.py`: comprobación del entorno.
- **Dependencias nuevas para este reto:** `rapidfuzz`, `openpyxl`, `plotly`, `pytest`.

## 6. Qué se pide construir (MVP)

Estructura propuesta (sustituye la parte de facturas del kit):
```
data/raw/                      Excel originales
core/suppliers.py              fichas de proveedores + diccionario geográfico
core/matching.py               generación de candidatos (nombre, ubicación, categoría)
core/judge.py                  esquema NewsAssessment + prompt few-shot + llamada a extract()
core/urgency.py                puntuación de dependencia + reglas de urgencia
core/pipeline.py               assess(news_row) -> resultado completo + explicación + acción
evaluate.py                    métricas sobre la validación
fill_test.py                   rellena el Excel de test
app.py                         panel Streamlit (alertas, mapa, proveedor, métricas)
bot/                           (fase 2, ver sección 7) Radar Bot de Telegram
core/geo.py, core/hazards.py   (fase 2, ver sección 8) alerta temprana y vulnerabilidad
n8n/supplier_alerts.json       flujo: programado → API → si es urgente → Teams/correo
```
**Requisitos:**
- Que funcione 100 % en local con Ollama.
- Que el código sea limpio, comentado en español y modular.
- Que haya un modo `--no-llm` (solo reglas) para probar sin GPU.
- Que se ejecute primero `evaluate.py` y se iteren los prompts y las reglas hasta maximizar el acierto en validación **sin usar las etiquetas de validación como ejemplos**.

## 7. Propuesta de valor adicional: Radar Bot (Telegram)

> **Prioridad:** construir esta parte **solo cuando el pipeline principal, `evaluate.py` y `fill_test.py` funcionen**. No puntúa en el test,
> pero es el elemento diferenciador del pitch: una alerta llegando en directo al móvil del jurado.

### Concepto
Asistente de mensajería para el **equipo de compras de Helixa**, con dos funciones:
1. **Alertas proactivas:** cuando el pipeline marca una noticia como urgente (o de riesgo) para un proveedor, avisa **solo a los compradores que siguen a ese proveedor**.
2. **Chatbot de consulta:** el comprador pregunta en lenguaje natural por un proveedor, una zona o un material y el bot responde con datos reales.

### Decisiones de diseño (y su justificación)
| Decisión | Justificación |
|---|---|
| **Telegram** en la demo; WhatsApp Business y Microsoft Teams como canales de producción | Telegram: bot gratis en 2 minutos (@BotFather), permite enviar mensajes sin que el usuario escriba antes y funciona en local con *polling*, sin URL pública. WhatsApp exige cuenta de Meta Business, plantillas aprobadas para mensajes fuera de la ventana de 24 h, un webhook HTTPS público y tiene coste por conversación. La arquitectura es la misma: solo cambia el conector |
| **"Proveedores recurrentes" = suscripciones** | Los datos no incluyen historial de compras. Cada comprador sigue proveedores o categorías (por ejemplo, el responsable de APIs sigue de S001 a S008). Se precargan por categoría y se gestionan con `/seguir` y `/dejar` |
| **No deshabilitar automáticamente** | El proveedor pasa a **"en riesgo · bloqueo temporal pendiente de revisión"** y una persona lo confirma con un botón. Bloquear de forma automática un proveedor único por una noticia podría parar la producción: el humano decide y la IA prepara la decisión |
| **El LLM no responde de memoria** | qwen2.5 en Ollama con **function calling** (`tools`): el modelo solo elige qué función llamar y redacta la respuesta con lo que devuelve. Así no se inventan datos y todo sigue siendo local y confidencial |

### Mensaje de alerta (ejemplo)
```
🔴 URGENTE · Taizhou Hengyuan Pharma (S003)
Incendio en el parque químico de Taizhou: inspecciones de al menos 3 semanas.
Proveedor ÚNICO de Metformina · 30 días de inventario · afecta a Glucora 850 mg.
Acción sugerida: revisar el stock y buscar un proveedor alternativo de urgencia.
[✅ Confirmar bloqueo]  [❌ Falsa alarma]  [📄 Ver noticia]
```
- **Confirmar bloqueo:** cambia el estado del proveedor a `bloqueado_temporal` en SQLite y lo registra en la auditoría (quién y cuándo).
- **Falsa alarma:** guarda la respuesta del comprador, que se usa para mejorar el sistema (ajuste de umbrales y nuevos ejemplos).
- Las noticias urgentes se envían al momento. Las de riesgo no urgente van en un resumen agrupado (`/resumen`, o programado semanalmente).

### Chatbot: funciones (tools) a exponer al LLM
| Función | Ejemplo de pregunta |
|---|---|
| `buscar_proveedor(nombre_o_id)` | "¿Qué sabes de Nordic Lipids?" → ficha + estado + últimos eventos |
| `riesgos_recientes(proveedor_id=None, dias=30)` | "¿Hay algún riesgo activo esta semana?" |
| `proveedores_en_zona(lugar)` | "¿Qué proveedores tenemos en Gujarat?" (usa el diccionario geográfico) |
| `alternativo_de(proveedor_id_o_material)` | "¿Quién puede sustituir a Sunrise BioChem?" |
| `productos_afectados(proveedor_id)` | "¿Qué medicamentos dependen de S017?" |

Comandos rápidos: `/start`, `/proveedor <nombre>`, `/alertas`, `/seguir <ID|categoría>`, `/dejar <ID>`, `/mis_proveedores`, `/resumen`.

### Implementación
- **Librería:** `python-telegram-bot` (v21+, asíncrona), en modo *polling*. Token en una variable de entorno `TELEGRAM_BOT_TOKEN` (fichero `.env`, nunca en el repositorio).
- **Ficheros nuevos:**
  ```
  bot/telegram_bot.py      comandos, mensajes libres → LLM con tools, callbacks de los botones
  bot/tools.py             funciones de consulta (SQLite + fichas de proveedores) + su JSON schema para Ollama
  bot/notifier.py          notify(assessment): busca suscriptores y envía la alerta con botones
  ```
- **Tablas SQLite nuevas:**
  - `subscribers(chat_id, nombre, rol)`
  - `subscriptions(chat_id, supplier_id | category)`
  - `supplier_status(supplier_id, estado, motivo, news_id, actualizado_por, ts)`
  - `feedback(news_id, chat_id, veredicto, ts)`
- **Integración:** `core/pipeline.py` llama a `notifier.notify()` cuando `is_risk` es verdadero, y usa urgencia inmediata o resumen según corresponda. El panel de Streamlit muestra el estado de los proveedores y las respuestas recibidas.
- **Modo demo:** un script `bot/demo_feed.py` "publica" las noticias del test o la validación una a una con un intervalo de unos 10 s, para que las alertas lleguen en directo durante el pitch.
- **Ollama con tools:** `POST /api/chat` con `"tools": [...]`. Se ejecutan las `tool_calls` devueltas y se vuelve a llamar con los resultados (como mucho 3 iteraciones).
- **Dependencias:** `python-telegram-bot>=21`, `python-dotenv`.
- **Esfuerzo estimado:** 4–6 horas.

### Mensaje para el pitch
"No sustituimos al comprador, le damos superpoderes: se entera antes que nadie, en el canal que ya usa,
con el contexto y la acción recomendada, y puede preguntar lo que necesite. La decisión de bloquear sigue siendo suya, y queda registrada."

## 8. Propuestas de valor adicionales: de reaccionar a anticipar

> **Idea central del pitch:** "Las noticias nos dicen lo que **ya ha pasado**. Nosotros añadimos lo que **va a pasar** (previsiones)
> y **dónde nos dolería más** (puntos únicos de fallo). La red de socios que reportan incidencias es el siguiente paso."
> **Prioridad:** después del pipeline principal y de evaluate.py/fill_test.py. Orden recomendado: 8.2 (casi gratis con los datos) → 8.1 → bot (sección 7) → 8.3 solo como roadmap.

### 8.1 Alerta temprana con datos abiertos (construir)
**Qué hace:** consulta periódicamente **previsiones y eventos en tiempo real** sobre la ubicación de cada proveedor y de sus nodos logísticos, y genera
señales de riesgo **antes** de que aparezcan las noticias.

| Fuente (gratuita, sin clave) | Qué detecta | Endpoint orientativo |
|---|---|---|
| Open-Meteo Forecast | Lluvia extrema, viento de tormenta o huracán, nieve, en un horizonte de 1 a 7 días | `https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..&daily=precipitation_sum,wind_gusts_10m_max&forecast_days=7` |
| Open-Meteo Flood | Caudal previsto de los ríos (inundaciones; también caudal bajo, como el del Rin) | `https://flood-api.open-meteo.com/v1/flood?latitude=..&longitude=..&daily=river_discharge` |
| USGS Earthquakes | Terremotos de magnitud ≥ 5,5 en un radio de N km de un proveedor | `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson` |

**Implementación:**
- `core/geo.py`: coordenadas (lat/lon) de cada ciudad de proveedor (tabla fija de 40 filas o geopy/Nominatim una sola vez y en caché).
- `core/hazards.py`: `scan_hazards()` → recorre los proveedores, llama a las APIs, aplica umbrales (por ejemplo ráfagas > 90 km/h, precipitación > 100 mm/día, terremoto ≥ 5,5 a < 150 km) y produce objetos `HazardSignal(supplier_ids, tipo, severidad, fecha_prevista, fuente)`.
- Las señales entran en **el mismo flujo** que las noticias (`source = "forecast"`): urgencia = gravedad × dependencia, alerta por bot o panel y auditoría.
- **Modo demo sin internet:** `data/hazards_demo.json` con previsiones simuladas que reproducen los eventos del dataset (huracán Delia en Puerto Rico → S025; tifón en Shanghái/Ningbo; inundaciones en Gujarat → S002/S006/S014; terremoto en el sur de Taiwán → S013; caudal bajo del Rin → S009/S039), fechadas **2–3 días antes** de la noticia correspondiente.
- **Visual del pitch:** línea temporal "previsión detectada (D-3) → noticia publicada (D0) → **días de anticipación ganados**".
- **Coste:** 0 €. **Esfuerzo:** 3–4 h. **Sin problemas de adopción:** no depende de que nadie colabore.
- **Pendiente de verificar:** comprobar los parámetros exactos de las APIs en su documentación antes de programar.

### 8.2 Mapa de puntos únicos de fallo (construir)
**Qué hace:** sin necesidad de ningún evento, muestra **dónde es vulnerable Helixa** y recomienda acciones preventivas.
- **Índice de vulnerabilidad por proveedor:** proveedor único + criticidad + días de inventario + existencia de alternativo + productos afectados.
- **Concentración geográfica:** proveedores que comparten zona (por ejemplo S002, S006 y S014 en Gujarat; S009 y S039 en el corredor del Rin; S030 y S038 en Rotterdam) → un solo evento afecta a varios a la vez.
- **Recomendaciones automáticas** a partir de los datos, por ejemplo: "Cualificar un alternativo para la Metformina (S003, proveedor único, 30 días)", "Subir la cobertura de inventario de S012", "Diversificar fuera de Gujarat".
- **Panel:** pestaña "Vulnerabilidad" con un mapa (círculos por proveedor, tamaño = gasto, color = índice), un ranking de los 10 más críticos y un gráfico de concentración por región.
- **Esfuerzo:** 2–3 h (solo pandas y Plotly sobre los datos existentes). **Valor:** es el informe que pediría un director de compras para decidir dónde invertir en resiliencia.

### 8.3 Red de señales de campo, "Waze del suministro" (roadmap, no construir salvo que sobre tiempo)
**Idea:** los **proveedores y transportistas contratados** (S030–S033 y los propios proveedores) reportan incidencias que ven sobre el terreno
(accidente, cierre de vía, puerto o aduana colapsados, meteorología, huelga, avería) desde el mismo bot de Telegram: `/incidencia` → botones de tipo → compartir ubicación → nota opcional.

**Diseño realista (justificación ante el jurado):**
| Riesgo | Mitigación |
|---|---|
| Los conductores no son de Helixa y no tienen motivo para reportar | Que reporten las **empresas socias**, con **obligación contractual** (aviso en menos de 2 h) e incentivos: mejor puntuación de proveedor y prioridad en contratos |
| Pocos usuarios, sin el "efecto red" de Waze | El valor no está en el volumen: está en que **quien lleva tu mercancía** avise de que va a retrasarse |
| Solo cubre el transporte, no incendios en planta ni quiebras | Es un **complemento** de las noticias y las previsiones, nunca un sustituto |
| Reportes falsos o caducados | Puntuación de fiabilidad por informante, caducidad automática y más confianza si coinciden varias fuentes |

**Validación de mercado:** existen empresas dedicadas a la visibilidad del transporte y al riesgo de proveedores en tiempo real (project44, FourKites, Everstream, Resilinc), lo que demuestra que hay demanda.
**Demo opcional (1–2 h si el bot ya existe):** un comando `/incidencia` que crea una señal con `source = "campo"` y aparece en el panel en segundos.

### 8.4 Cómo justificar el valor económico (sin inventar cifras)
Añadir a la pestaña **Impacto** una calculadora con **supuestos editables y visibles**:
- **Fletes urgentes evitados:** incidentes al año × % detectados con antelación × (coste del flete aéreo − coste del transporte habitual).
- **Roturas de stock evitadas:** días de parada evitados × coste de un día de línea parada. Usar `Monthly_Requirement` e `Inventory_Cover_Days` de los datos.
- **Capital liberado:** reducción de los días de inventario de seguridad en materiales no críticos × gasto diario (`Annual_Spend_EUR` / 365).
- **Métrica estrella:** **días de anticipación ganados** frente a enterarse por la noticia o por el pedido que no llega.
> No presentar cifras de mercado como hechos sin una fuente citada. Si se usan, buscar la fuente y citarla en la diapositiva.

---

## Anexo A · Proveedores (hoja Suppliers, columnas principales)

| Supplier_ID   | Supplier_Name                   | Category              | Material_Supplied                        | Country           | City             | Single_Source   | Approved_Alternate_ID   | Criticality   |   Inventory_Cover_Days |
|:--------------|:--------------------------------|:----------------------|:-----------------------------------------|:------------------|:-----------------|:----------------|:------------------------|:--------------|-----------------------:|
| S001          | Sunrise BioChem Ltd             | API                   | Amoxicillin trihydrate                   | India             | Hyderabad        | N               | S002                    | High          |                     45 |
| S002          | Kaveri Fine Chemicals           | API                   | Amoxicillin trihydrate                   | India             | Ahmedabad        | N               | S001                    | High          |                     45 |
| S003          | Taizhou Hengyuan Pharma         | API                   | Metformin hydrochloride                  | China             | Taizhou          | Y               |                         | High          |                     30 |
| S004          | Orion Synthesis AG              | API                   | Atorvastatin calcium                     | Switzerland       | Basel            | N               | S005                    | High          |                     60 |
| S005          | Wuhan Lotus Chemicals           | API                   | Atorvastatin calcium                     | China             | Wuhan            | N               | S004                    | High          |                     60 |
| S006          | Narmada Lifesciences            | API                   | Paracetamol                              | India             | Ahmedabad        | N               | S007                    | Medium        |                     50 |
| S007          | Huaxin Pharmaceutical Materials | API                   | Paracetamol                              | China             | Shanghai         | N               | S006                    | Medium        |                     50 |
| S008          | Celtic BioLogics Ltd            | API                   | Monoclonal antibody drug substance       | Ireland           | Cork             | Y               |                         | High          |                     90 |
| S009          | Rhenvale Excipients GmbH        | Excipients            | Microcrystalline cellulose               | Germany           | Ludwigshafen     | N               | S010                    | Medium        |                     40 |
| S010          | Lombardia Polymers SpA          | Excipients            | Microcrystalline cellulose               | Italy             | Milan            | N               | S009                    | Medium        |                     40 |
| S011          | Iberia Starch & Sugars          | Excipients            | Pregelatinised starch                    | Spain             | Valencia         | Y               |                         | Medium        |                     35 |
| S012          | Nordic Lipids AS                | Excipients            | Lipid nanoparticle components            | Norway            | Oslo             | Y               |                         | High          |                     30 |
| S013          | Pacific Magnesium Co.           | Excipients            | Magnesium stearate                       | Taiwan            | Kaohsiung        | N               | S014                    | Medium        |                     40 |
| S014          | Gujarat Minerals & Salts        | Excipients            | Magnesium stearate                       | India             | Vadodara         | N               | S013                    | Medium        |                     40 |
| S015          | Lumina Glassworks               | Primary packaging     | Type I glass vials                       | Germany           | Mainz            | N               | S016                    | High          |                     35 |
| S016          | Vitrum Medica SpA               | Primary packaging     | Type I glass vials                       | Italy             | Bergamo          | N               | S015                    | High          |                     35 |
| S017          | Stellar Elastomers Inc.         | Primary packaging     | Rubber stoppers                          | USA               | Lancaster        | Y               |                         | High          |                     40 |
| S018          | Medipack Iberica SL             | Primary packaging     | Aluminium blister foil                   | Spain             | Barcelona        | N               | S019                    | Medium        |                     30 |
| S019          | Polaris Films Sp. z o.o.        | Primary packaging     | Aluminium blister foil                   | Poland            | Lodz             | N               | S018                    | Medium        |                     30 |
| S020          | Kansai PreFill Co.              | Primary packaging     | Pre-filled syringe barrels               | Japan             | Osaka            | Y               |                         | High          |                     45 |
| S021          | Andes Cartonaje                 | Secondary packaging   | Folding cartons                          | Mexico            | Monterrey        | N               | S022                    | Low           |                     25 |
| S022          | Benelux Print & Pack            | Secondary packaging   | Folding cartons                          | Belgium           | Antwerp          | N               | S021                    | Low           |                     25 |
| S023          | LabelCraft Ireland              | Secondary packaging   | Serialised labels                        | Ireland           | Dublin           | Y               |                         | Medium        |                     20 |
| S024          | Zhejiang Paper Leaflets         | Secondary packaging   | Patient information leaflets             | China             | Hangzhou         | Y               |                         | Low           |                     30 |
| S025          | Celsius Bioprocess Systems      | Single-use bioprocess | Bioreactor bags                          | Puerto Rico (USA) | San Juan         | Y               |                         | High          |                     40 |
| S026          | Alpine Filtration AG            | Single-use bioprocess | Sterile filters                          | Switzerland       | Zurich           | N               | S027                    | High          |                     45 |
| S027          | Hsinchu Membrane Tech           | Single-use bioprocess | Sterile filters                          | Taiwan            | Hsinchu          | N               | S026                    | High          |                     45 |
| S028          | Darmstadt Reagent Works         | Lab reagents          | Chromatography resins                    | Germany           | Darmstadt        | Y               |                         | Medium        |                     60 |
| S029          | Boston Assay Supplies           | Lab reagents          | Quality control assay kits               | USA               | Boston           | Y               |                         | Low           |                     30 |
| S030          | PolarChain Logistics            | Logistics             | Temperature-controlled road freight (EU) | Netherlands       | Rotterdam        | N               | S031                    | High          |                        |
| S031          | TransAlp Cold Freight           | Logistics             | Temperature-controlled road freight (EU) | Switzerland       | Basel            | N               | S030                    | High          |                        |
| S032          | Oceanbridge Shipping Agency     | Logistics             | Asia to Europe sea freight               | Singapore         | Singapore        | N               | S033                    | Medium        |                        |
| S033          | Silkroute Rail Freight          | Logistics             | Asia to Europe rail freight              | China             | Xi'an            | N               | S032                    | Medium        |                        |
| S034          | Cyprin Analytical Services      | Services              | Batch release testing laboratory         | India             | Bengaluru        | Y               |                         | Medium        |                        |
| S035          | Vectra Serialisation Software   | Services              | Track-and-trace serialisation platform   | Spain             | Madrid           | Y               |                         | High          |                        |
| S036          | Aurum Gelatin Capsules          | Excipients            | Hard gelatin capsules                    | Brazil            | Sao Paulo        | N               | S037                    | Medium        |                     40 |
| S037          | Biocaps Vietnam                 | Excipients            | Hard gelatin capsules                    | Vietnam           | Ho Chi Minh City | N               | S036                    | Medium        |                     40 |
| S038          | Rotterdam Solvent Distribution  | Chemicals             | Process solvents                         | Netherlands       | Rotterdam        | N               | S039                    | Medium        |                     20 |
| S039          | Rhine Valley Solvents GmbH      | Chemicals             | Process solvents                         | Germany           | Cologne          | N               | S038                    | Medium        |                     20 |
| S040          | Atlas Cleanroom Garments        | Consumables           | Cleanroom garments                       | Morocco           | Tangier          | Y               |                         | Low           |                     45 |

## Anexo B · Materiales (hoja Materials)

| Material_ID   | Material                           | Category              | Primary_Supplier_ID   | Primary_Supplier_Name      | Alternate_Supplier_ID   | Alternate_Supplier_Name         | Used_In_Products                                                                              |   Monthly_Requirement | Unit   |
|:--------------|:-----------------------------------|:----------------------|:----------------------|:---------------------------|:------------------------|:--------------------------------|:----------------------------------------------------------------------------------------------|----------------------:|:-------|
| M01           | Amoxicillin trihydrate             | API                   | S001                  | Sunrise BioChem Ltd        | S002                    | Kaveri Fine Chemicals           | Amoxira 500 mg capsules                                                                       |                  1200 | kg     |
| M02           | Metformin hydrochloride            | API                   | S003                  | Taizhou Hengyuan Pharma    |                         |                                 | Glucora 850 mg tablets                                                                        |                  3500 | kg     |
| M03           | Atorvastatin calcium               | API                   | S004                  | Orion Synthesis AG         | S005                    | Wuhan Lotus Chemicals           | Lipivia 20 mg tablets                                                                         |                    80 | kg     |
| M04           | Paracetamol                        | API                   | S006                  | Narmada Lifesciences       | S007                    | Huaxin Pharmaceutical Materials | Fevrex 500 mg tablets                                                                         |                  2600 | kg     |
| M05           | Monoclonal antibody drug substance | API                   | S008                  | Celtic BioLogics Ltd       |                         |                                 | HX-mAb 100 mg injection                                                                       |                    12 | kg     |
| M06           | Microcrystalline cellulose         | Excipients            | S009                  | Rhenvale Excipients GmbH   | S010                    | Lombardia Polymers SpA          | Glucora 850 mg tablets; Lipivia 20 mg tablets                                                 |                  5200 | kg     |
| M07           | Pregelatinised starch              | Excipients            | S011                  | Iberia Starch & Sugars     |                         |                                 | Fevrex 500 mg tablets; Glucora 850 mg tablets                                                 |                  1800 | kg     |
| M08           | Lipid nanoparticle components      | Excipients            | S012                  | Nordic Lipids AS           |                         |                                 | HX-RSV mRNA vaccine                                                                           |                    40 | kg     |
| M09           | Magnesium stearate                 | Excipients            | S013                  | Pacific Magnesium Co.      | S014                    | Gujarat Minerals & Salts        | Glucora 850 mg tablets; Lipivia 20 mg tablets                                                 |                   300 | kg     |
| M10           | Hard gelatin capsules              | Excipients            | S036                  | Aurum Gelatin Capsules     | S037                    | Biocaps Vietnam                 | Amoxira 500 mg capsules                                                                       |               2400000 | units  |
| M11           | Type I glass vials                 | Primary packaging     | S015                  | Lumina Glassworks          | S016                    | Vitrum Medica SpA               | HX-mAb 100 mg injection                                                                       |                450000 | units  |
| M12           | Rubber stoppers                    | Primary packaging     | S017                  | Stellar Elastomers Inc.    |                         |                                 | HX-mAb 100 mg injection                                                                       |                450000 | units  |
| M13           | Aluminium blister foil             | Primary packaging     | S018                  | Medipack Iberica SL        | S019                    | Polaris Films Sp. z o.o.        | Amoxira 500 mg capsules; Fevrex 500 mg tablets; Glucora 850 mg tablets; Lipivia 20 mg tablets |                  9000 | m2     |
| M14           | Pre-filled syringe barrels         | Primary packaging     | S020                  | Kansai PreFill Co.         |                         |                                 | HX-RSV mRNA vaccine                                                                           |                600000 | units  |
| M15           | Folding cartons                    | Secondary packaging   | S022                  | Benelux Print & Pack       | S021                    | Andes Cartonaje                 | Amoxira 500 mg capsules; Fevrex 500 mg tablets; Glucora 850 mg tablets; Lipivia 20 mg tablets |                900000 | units  |
| M16           | Patient information leaflets       | Secondary packaging   | S024                  | Zhejiang Paper Leaflets    |                         |                                 | Amoxira 500 mg capsules; Glucora 850 mg tablets                                               |                900000 | units  |
| M17           | Serialised labels                  | Secondary packaging   | S023                  | LabelCraft Ireland         |                         |                                 | HX-RSV mRNA vaccine; HX-mAb 100 mg injection                                                  |               1050000 | units  |
| M18           | Bioreactor bags                    | Single-use bioprocess | S025                  | Celsius Bioprocess Systems |                         |                                 | HX-mAb 100 mg injection                                                                       |                    60 | units  |
| M19           | Sterile filters                    | Single-use bioprocess | S026                  | Alpine Filtration AG       | S027                    | Hsinchu Membrane Tech           | HX-RSV mRNA vaccine; HX-mAb 100 mg injection                                                  |                  1500 | units  |
| M20           | Chromatography resins              | Lab reagents          | S028                  | Darmstadt Reagent Works    |                         |                                 | HX-mAb 100 mg injection                                                                       |                    90 | litres |

## Anexo C · Noticias de entrenamiento con sus etiquetas y explicaciones

| News_ID   | Headline                                                                                     | Is_Risk   | Urgent   | Affected_Supplier_IDs   | Event_Type                | Explanation                                                                                                                                                                                                        |
|:----------|:---------------------------------------------------------------------------------------------|:----------|:---------|:------------------------|:--------------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| N001      | Fire at Taizhou chemical park forces evacuation of several API plants                        | Y         | Y        | S003                    | Fire / plant incident     | Risk to S003 Taizhou Hengyuan Pharma (named in the article). Urgent: this fire / plant incident can stop or seriously delay supply soon.                                                                           |
| N002      | Central bank holds interest rates steady                                                     | N         | N        |                         | Not relevant              | Not a risk: no link to any Helixa supplier.                                                                                                                                                                        |
| N005      | Global smartphone shipments rise 4 percent in third quarter                                  | N         | N        |                         | Not relevant              | Not a risk: no link to any Helixa supplier.                                                                                                                                                                        |
| N006      | Severe flooding in Gujarat disrupts industrial estates around Ahmedabad and Vadodara         | Y         | Y        | S002; S006; S014        | Natural disaster          | Risk to S002 Kaveri Fine Chemicals, S006 Narmada Lifesciences, S014 Gujarat Minerals & Salts (located in the affected area). Urgent: this natural disaster can stop or seriously delay supply soon.                |
| N007      | Orion Capital raises USD 2 billion for new technology fund                                   | N         | N        |                         | Not relevant              | Not a risk: the name looks like S004 Orion Synthesis AG, but the article is about a different organisation or topic.                                                                                               |
| N011      | Magnitude 6.8 earthquake strikes southern Taiwan                                             | Y         | N        | S013                    | Natural disaster          | Risk to S013 Pacific Magnesium Co. (located in the affected area). Not urgent: natural disaster with limited or short-lived impact, so it can wait for the regular report.                                         |
| N013      | Heavy rain expected in Mumbai this weekend                                                   | N         | N        |                         | Not relevant              | Not a risk: it mentions a place where a supplier is based, but describes nothing that affects supply.                                                                                                              |
| N014      | Stellar Elastomers announces voluntary recall of rubber stopper lots                         | Y         | Y        | S017                    | Quality recall            | Risk to S017 Stellar Elastomers Inc. (named in the article). Urgent: this quality recall can stop or seriously delay supply soon.                                                                                  |
| N015      | Swiss franc strengthens against the euro                                                     | N         | N        |                         | Not relevant              | Not a risk: no link to any Helixa supplier.                                                                                                                                                                        |
| N017      | 'Lumina' tops the box office in its opening weekend                                          | N         | N        |                         | Not relevant              | Not a risk: the name looks like S015 Lumina Glassworks, but the article is about a different organisation or topic.                                                                                                |
| N018      | Veltrix Pharma agrees to acquire syringe maker Kansai PreFill                                | Y         | N        | S020                    | Acquisition by competitor | Risk to S020 Kansai PreFill Co. (named in the article). Not urgent: acquisition by competitor with limited or short-lived impact, so it can wait for the regular report.                                           |
| N020      | Authorities suspend production licence of Wuhan Lotus Chemicals pending environmental review | Y         | Y        | S005                    | Regulatory action         | Risk to S005 Wuhan Lotus Chemicals (named in the article). Urgent: this regulatory action can stop or seriously delay supply soon.                                                                                 |
| N025      | PolarChain Logistics chief executive steps down                                              | Y         | N        | S030                    | Leadership change         | Risk to S030 PolarChain Logistics (named in the article). Not urgent: leadership change with limited or short-lived impact, so it can wait for the regular report.                                                 |
| N028      | Cork airport passenger numbers reach record                                                  | N         | N        |                         | Not relevant              | Not a risk: it mentions Cork, where S008 Celtic BioLogics Ltd is based, but describes nothing that affects supply.                                                                                                 |
| N029      | Hurricane Delia makes landfall in Puerto Rico, island-wide power outages                     | Y         | Y        | S025                    | Natural disaster          | Risk to S025 Celsius Bioprocess Systems (located in the affected area). Urgent: this natural disaster can stop or seriously delay supply soon.                                                                     |
| N030      | Celtic beat Rangers 2-1 in Glasgow derby                                                     | N         | N        |                         | Not relevant              | Not a risk: the name looks like S008 Celtic BioLogics, but the article is about a different organisation or topic.                                                                                                 |
| N033      | Sunrise BioChem completes US inspection with no observations                                 | N         | N        | S001                    | Positive news             | Not a risk: positive news about S001 Sunrise BioChem Ltd.                                                                                                                                                          |
| N035      | Celtic BioLogics doubles drug substance capacity at Cork site                                | N         | N        | S008                    | Positive news             | Not a risk: positive news about S008 Celtic BioLogics Ltd.                                                                                                                                                         |
| N037      | Low water on the Rhine restricts barge traffic for chemical shippers                         | Y         | N        | S039; S009              | Logistics disruption      | Risk to S039 Rhine Valley Solvents GmbH, S009 Rhenvale Excipients GmbH (located in the affected area). Not urgent: logistics disruption with limited or short-lived impact, so it can wait for the regular report. |
| N039      | Shipping lines reroute around Africa as Red Sea tensions escalate                            | Y         | N        | S032                    | Logistics disruption      | Risk to S032 Oceanbridge Shipping Agency (located in the affected area). Not urgent: logistics disruption with limited or short-lived impact, so it can wait for the regular report.                               |
| N040      | European Parliament debates reform of pharmaceutical legislation                             | N         | N        |                         | Not relevant              | Not a risk: no link to any Helixa supplier.                                                                                                                                                                        |
| N042      | Shanghai hosts World AI Conference                                                           | N         | N        |                         | Not relevant              | Not a risk: it mentions Shanghai, where S007 Huaxin Pharmaceutical Materials is based, but describes nothing that affects supply.                                                                                  |
| N045      | Lodz to host European logistics summit                                                       | N         | N        |                         | Not relevant              | Not a risk: it mentions Lodz, where S019 Polaris Films Sp. z o.o. is based, but describes nothing that affects supply.                                                                                             |
| N046      | Spanish truckers' association calls nationwide strike next week                              | Y         | N        | S018; S011              | Labour strike             | Risk to S018 Medipack Iberica SL, S011 Iberia Starch & Sugars (located in the affected area). Not urgent: labour strike with limited or short-lived impact, so it can wait for the regular report.                 |
| N048      | Sunrise Energy commissions 500 MW solar farm in Rajasthan                                    | N         | N        |                         | Not relevant              | Not a risk: the name looks like S001 Sunrise BioChem (also in India), but the article is about a different organisation or topic.                                                                                  |
| N050      | Rating agency downgrades Iberia Starch & Sugars to B-                                        | Y         | N        | S011                    | Financial distress        | Risk to S011 Iberia Starch & Sugars (named in the article). Not urgent: financial distress with limited or short-lived impact, so it can wait for the regular report.                                              |
| N053      | Strike at Rotterdam container terminals enters third day                                     | Y         | N        | S030; S038              | Labour strike             | Risk to S030 PolarChain Logistics, S038 Rotterdam Solvent Distribution (located in the affected area). Not urgent: labour strike with limited or short-lived impact, so it can wait for the regular report.        |
| N054      | Biocaps Vietnam signs long-term supply deal with European pharma group                       | N         | N        | S037                    | Positive news             | Not a risk: positive news about S037 Biocaps Vietnam.                                                                                                                                                              |
| N057      | Protests block highway near Hsinchu science park for second day                              | Y         | N        | S027                    | Logistics disruption      | Risk to S027 Hsinchu Membrane Tech (located in the affected area). Not urgent: logistics disruption with limited or short-lived impact, so it can wait for the regular report.                                     |
| N058      | Dublin hosts European fintech week                                                           | N         | N        |                         | Not relevant              | Not a risk: it mentions Dublin, where S023 LabelCraft Ireland is based, but describes nothing that affects supply.                                                                                                 |
