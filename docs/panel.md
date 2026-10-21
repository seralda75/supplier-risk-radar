# Panel: elementos clicables y rendimiento

## 1. Inventario de elementos clicables

Cada elemento se ha comprobado con clics de ratón reales (Playwright, Edge, sin internet): se pulsa en sus
coordenadas, como un usuario, y se comprueba qué cambia en la pantalla y en SQLite.

| Página | Elemento | Qué hace |
|---|---|---|
| Todas | Menú lateral (4 entradas) | `st.page_link` de `st.navigation`: enlace real con su URL (`/proveedores`, `/simulador`, `/transparencia`); solo se ejecuta la página activa |
| Centro de control | Selector de noticias (test, validación, entrenamiento) | Cambia el conjunto |
| Centro de control | «Simular escenario» | Enlace al simulador |
| Centro de control | «Revisar ahora» (banner) | Elige la crítica **pendiente** con menos margen |
| Centro de control | Tarjeta de «Requiere tu decisión» o fila «En seguimiento semanal» | La elige (detalle a la derecha) y abre su **ventana** (centrada, fondo difuminado) |
| Centro de control · detalle | «Ver noticia original» | Desplegable con fuente, fecha, tipo de evento, titular y resumen (el reto no trae enlaces) |
| Centro de control · detalle y ventana | «Aprobar plan» | Guarda en SQLite, avisa, la tarjeta pasa a «✓ PLAN APROBADO», baja el KPI de críticas sin decidir y aparece la confirmación (quién y cuándo) |
| Centro de control · detalle y ventana | «Falsa alarma» | Pide un motivo (opcional) y lo guarda; la alerta sale de los KPIs, el calendario, el mapa y el treemap; la tarjeta queda tachada |
| Centro de control · detalle y ventana | «Reabrir» | Deja la alerta pendiente otra vez; la auditoría conserva las dos decisiones |
| Centro de control · detalle | «Crear pedido o recordatorio» | Abre la ventana de la alerta |
| Ventana de la alerta | «Crear pedido» | Formulario prellenado (material, proveedor según el plan, cantidad = necesidad mensual × días de déficit / 30 con el cálculo explicado, fecha requerida, prioridad). Se guarda como «Pedido pendiente de envío al ERP» (no se envía) |
| Ventana de la alerta | «Crear recordatorio» | Texto (el primer paso del plan), responsable y fecha. Se guarda en SQLite |
| Ventana de la alerta | X o pulsar fuera | Cierra la ventana |
| Centro de control | «Acciones en curso» · «Hecho» | Marca el pedido o el recordatorio como hecho (pasa a «Hechas») |
| Centro de control | Puntos del mapa | Abren la ficha del proveedor (ventana) |
| Centro de control | Casilla de un proveedor del treemap | Abre su ficha (ventana) |
| Centro de control | Casilla «Otros sin riesgo (N)» del treemap | Abre la lista de esos proveedores; cada uno abre su ficha |
| Proveedores | Buscador de la cabecera | Abre la ficha del proveedor elegido (ventana) |
| Proveedores | Filas del ranking de vulnerabilidad | Abren la ficha (ventana) |
| Simulador | Texto, «Interpretar con la IA», ejemplos, «Usar este ejemplo», formulario y «Calcular impacto» | Como antes |
| Simulador | Puntos del mapa | Abren la ficha |
| Transparencia | Dos desplegables (historial y documento de evaluación) | Como antes |

Las tarjetas, filas y casillas son HTML propio, pero lo que se pulsa es siempre un widget real de Streamlit: un
`st.button` invisible encima (cola, ranking, lista), botones de un componente `st.components.v2` (treemap) o la
selección de puntos de `st.plotly_chart` (mapa).

### «Aprobar plan» y «Falsa alarma» no hacían nada

No se pudo reproducir con la versión anterior: con clics reales en Edge, Chrome y Firefox, en cinco anchos y con
zoom, y en nueve recorridos (cambiar de página y volver, elegir otra tarjeta, «Revisar ahora», abrir la ficha…)
la decisión siempre se guardaba. Lo que sí se vio: la base de datos del revisor no tenía ninguna decisión, así
que sus clics no llegaron al servidor.

Lo que se ha cambiado para que no vuelva a pasar:

- **Sin estado intermedio.** Antes: un callback guardaba y dejaba banderas en `session_state` que el fragmento
  leía en la ejecución siguiente («volver a ejecutar la página entera», «mostrar el aviso»). Ahora:
  `if st.button(...)` → se guarda en SQLite → `st.rerun()` de la página entera. KPIs, tarjeta, calendario, mapa
  y treemap salen ya con la decisión.
- **La tarjeta no se mueve.** Antes, al decidir, la tarjeta saltaba al final de la cola y parecía que no había
  pasado nada; ahora se queda en su sitio y cambia de aspecto.
- **Avisos abajo a la derecha.** Fallo real encontrado con los clics: el aviso de una decisión (arriba a la
  derecha, unos 4 s) tapaba la X de la siguiente ventana, y ese clic se perdía.

## 2. Interacciones probadas con clic real (última pasada)

| Interacción | Resultado |
|---|---|
| «Aprobar plan» en el detalle | SQLite `plan_aprobado`, aviso, tarjeta «✓ PLAN APROBADO», KPI críticas 5 → 4, confirmación |
| «Reabrir» | Vuelve a pendiente, KPI 4 → 5 |
| «Falsa alarma» con motivo en el detalle | SQLite `falsa_alarma` + motivo, proveedores expuestos 11 → 10, tarjeta tachada, motivo en la confirmación |
| Tarjeta de la cola | Abre la ventana con fondo difuminado: noticia, impacto, calendario, plan y decisión |
| «Crear pedido» en la ventana | SQLite `orders` (pendiente_erp); la ventana sigue abierta con la confirmación |
| «Crear recordatorio» en la ventana | SQLite `reminders` |
| «Aprobar plan» en la ventana | Se guarda y la ventana se cierra; la tarjeta muestra «📦 Pedido creado · ⏰ Recordatorio 21 oct» |
| «Acciones en curso» · «Hecho» | Estado `hecho` en SQLite |
| «Falsa alarma» con motivo en la ventana | Se guarda con el motivo y la ventana se cierra |
| X de la ventana, también justo después de una decisión | Se cierra; la siguiente tarjeta abre su ventana |
| «Revisar ahora» | Selecciona la crítica pendiente con menos margen |
| «Ver noticia original» | Noticia completa |
| «Crear pedido o recordatorio» en el detalle | Abre la ventana de esa alerta |
| Punto del mapa | Ficha del proveedor |
| Casilla del treemap | Ficha del proveedor |
| Casilla «Otros sin riesgo» → proveedor de la lista | Lista de 5 proveedores → su ficha |
| «Simular escenario» | `/simulador` |
| Fila del ranking · buscador de Proveedores | Ficha del proveedor |
| Proveedores: fila de dos tarjetas | Misma altura (680 px y 680 px) |
| Simulador: ejemplo + «Calcular impacto» | Resultado con el plan |
| Menú lateral (4 páginas) | Cambia de página |

Sin excepciones y sin ninguna petición fuera de `localhost`. El treemap tiene 19 casillas y ninguna vacía.

## 3. Modo demo y agente de comunicaciones: latencia

Medido con `python scripts/latency_demo.py` el 21 oct 2026, **con el portátil en batería** (no estaba
enchufado: la GPU va más lenta; hay que repetirlo enchufado). Ollama con qwen2.5:7b, modelo ya cargado.

| Función | IA en directo (sin caché) | Con caché |
|---|---:|---:|
| Pipeline de una noticia (assess) | mediana 31,5 s (26–38 s, n = 5) | 0,1 s |
| Comunicaciones de una alerta | mediana 27,4 s (25–32 s, n = 5) | al instante |
| Plantilla de comunicaciones (sin IA) | — | < 0,01 s |

En el panel, del clic en «Simular noticia entrante» a la alerta en la cola (clics reales, en batería): 22–35 s
con IA en directo y ~9,7 s con caché, de los que 8,4 s son las pausas para que el público siga cada paso
(`DEMO_STEP_S`, `DEMO_END_S`). La primera noticia con caché tardó 19,4 s (carga de la base de ejemplos); el
modo demo ahora la precarga al activarse. «Preparar comunicaciones» con la respuesta en caché: 2,2–2,8 s
del clic a los borradores en pantalla.

Si la IA en directo tarda más de 60 s (`LIVE_TIMEOUT_S`), la demo usa el resultado precalculado y lo dice.

## 4. Rendimiento

Medido con Playwright: tiempo desde el clic hasta que la pantalla queda dibujada. Es decir, hasta que Streamlit
termina la ejecución y el DOM lleva 400 ms sin cambios. Se toma la mediana de varias repeticiones; la primera
visita a cada página se descarta.

Medido en la versión anterior (commit f7759a0), antes de la ventana de alerta y de la nueva distribución; no se ha vuelto a medir.

**Medición principal: mismas condiciones.** La versión anterior (commit 4d92806) y la actual se midieron
alternándose, dos rondas cada una, con el portátil en batería (CPU limitada). La tabla da la media de las
medianas de las dos rondas; las rondas difieren menos de un 10 %.

| Acción | Antes | Después | Mejora |
|---|---:|---:|---:|
| Cambiar a Proveedores | 2 508 ms | 475 ms | ×5,3 |
| Cambiar al Simulador | 2 460 ms | 296 ms | ×8,3 |
| Cambiar a Transparencia | 2 608 ms | 442 ms | ×5,9 |
| Cambiar al Centro de control | 3 140 ms | 824 ms | ×3,8 |
| Seleccionar una alerta de la cola | 2 582 ms | 345 ms | ×7,5 |
| «Revisar ahora» | 2 571 ms | 363 ms | ×7,1 |
| «Aprobar plan» | 2 574 ms | 372 ms | ×6,9 |

**Medición con el portátil enchufado.** Se hizo antes de los dos últimos cambios (treemap en HTML y mapa sin
fronteras), así que el Centro de control actual debería ir algo más rápido que lo que indica la tabla:

| Acción | Antes | Después |
|---|---:|---:|
| Cambiar a Proveedores / Simulador / Transparencia | 2 240–2 293 ms | 129–172 ms |
| Cambiar al Centro de control | 2 432 ms | 419 ms |
| Seleccionar una alerta | 2 284 ms | 136 ms |
| «Revisar ahora» / «Aprobar plan» | 2 293–2 307 ms | 160–198 ms |

**Objetivo de 300 ms:**

- **Enchufado:** se cumple en todo salvo al entrar en el Centro de control (419 ms medidos con el treemap de
  Plotly, que costaba unos 100 ms).
- **En batería:** solo se cumple en el simulador.
- **Centro de control:** es la página más pesada, con dos gráficos y unas 40 tarjetas, cajas y pasos. Dentro de
  ella, lo que se usa a cada momento (elegir una alerta o decidir) se queda entre 136 y 198 ms enchufado.

### Qué se cambió

| Cambio | Efecto |
|---|---|
| `OLLAMA_URL` con `127.0.0.1` en lugar de `localhost` | En Windows, `localhost` prueba antes IPv6 y cada llamada a Ollama perdía unos 2 s. El panel la hacía en cada clic: era casi todo el tiempo (2,1 s de 2,3 s) |
| Comprobación de Ollama cacheada 30 s, con un timeout de 0,5 s | Ya no se pregunta en cada clic. Si Ollama está apagado, como mucho cuesta 0,5 s cada 30 s |
| `st.navigation` con `st.Page` (`views/`) | Solo se ejecuta la página activa |
| Fragmento `st.fragment` con banner, KPIs, cola y detalle | Elegir una tarjeta, «Revisar ahora», «Aprobar plan» o «Reabrir» no vuelven a ejecutar ni a dibujar los gráficos. «Falsa alarma» redibuja la página entera porque cambia la exposición |
| `st.cache_data` | Resultados JSON, alertas, ejemplos del simulador, documentos y la figura del mapa |
| `st.cache_resource` | La conexión a SQLite |
| Excel y fichas | Se leen una vez por proceso (`lru_cache` en `core/`, que también usan los scripts y el bot sin Streamlit) |
| CSS en una sola llamada | Una constante calculada al importar. Las fuentes se declaran en `config.toml` y se sirven desde `static/` |
| Treemap en HTML (`st.components.v2`) en lugar de Plotly | Cada gráfico de Plotly cuesta unos 100 ms en montarse en el navegador. El treemap en HTML cuesta entre 20 y 45 ms |
| Mapa sin fronteras entre países | Unos 70 ms menos al dibujarlo |
