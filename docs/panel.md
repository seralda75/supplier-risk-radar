# Panel: elementos clicables y rendimiento

## 1. Inventario de elementos clicables

Revisado con capturas automáticas (Playwright, sin internet): cada elemento se pulsó y se comprobó qué cambiaba.

| Página | Elemento | Antes | Ahora |
|---|---|---|---|
| Todas | Menú lateral (4 entradas) | `st.button` que cambiaba una variable y recargaba toda la app | `st.page_link` de `st.navigation`: enlace real con su URL (`/proveedores`, `/simulador`, `/transparencia`); solo se ejecuta la página activa |
| Centro de control | Selector de noticias (test, validación, entrenamiento) | Funcionaba | Igual |
| Centro de control | «Simular escenario» | `st.button` | `st.page_link` al simulador |
| Centro de control | «Revisar ahora» (banner) | Elegía la crítica con menos margen, aunque ya estuviera decidida | Elige la crítica **pendiente** con menos margen; solo se redibuja la zona de decisión |
| Centro de control | Tarjetas de la cola y filas «En seguimiento semanal» | HTML con un `st.button` invisible encima: funcionaban | Igual, y muestran el estado de la decisión (plan aprobado, falsa alarma) |
| Centro de control | «Ver noticia original» | `<details>` de HTML: se abría en el navegador, sin pasar por Python | `st.popover`: fuente, fecha, tipo de evento, titular y resumen (el reto no trae enlaces) |
| Centro de control | «Aprobar plan» | Guardaba en SQLite y mostraba un aviso; la tarjeta solo añadía un chip pequeño y los KPIs no cambiaban | Guarda, avisa, muestra la confirmación (quién y cuándo), la tarjeta pasa a «✓ PLAN APROBADO» y baja el KPI de críticas sin decidir |
| Centro de control | «Falsa alarma» | Igual que «Aprobar plan» | Guarda y avisa; la tarjeta queda tachada como «FALSA ALARMA · DESCARTADA» y la alerta deja de contar en los KPIs, el calendario, el mapa y el treemap |
| Centro de control | «Reabrir» | No existía (una decisión no se podía deshacer) | Vuelve a dejar la alerta pendiente; la auditoría conserva las dos decisiones |
| Centro de control | Puntos del mapa | Solo información al pasar el ratón | Abren la ficha del proveedor (diálogo) |
| Centro de control | «¿Cuánto aguantamos?» (barras HTML) | No clicable | Sustituido por el calendario de roturas; no es clicable ni lo parece |
| Centro de control | Treemap «¿Dónde está el gasto en riesgo?» | — | Cada casilla es un botón que abre la ficha |
| Proveedores | Filas del ranking de vulnerabilidad | Tabla HTML sin acción | Cada fila abre la ficha y la deja elegida en «Ficha de proveedor» |
| Proveedores | Selector «Ficha de proveedor» | Funcionaba | Igual |
| Simulador | Texto, «Interpretar con la IA», ejemplos, «Usar este ejemplo», formulario y «Calcular impacto» | Funcionaban | Igual |
| Simulador | Puntos del mapa | Solo información al pasar el ratón | Abren la ficha |
| Transparencia | Dos desplegables (historial y documento de evaluación) | Funcionaban | Igual |

No queda ningún elemento con aspecto de clicable que no haga nada. Las tarjetas, las filas y las casillas son
HTML propio, pero lo que se pulsa es siempre un widget real de Streamlit:

- En la cola y el ranking, un `st.button` invisible colocado encima de cada tarjeta o fila.
- En el treemap, botones de un componente `st.components.v2` que devuelven el ID a Python.
- En el mapa, la selección de puntos de `st.plotly_chart`.

## 2. Rendimiento

Medido con Playwright: tiempo desde el clic hasta que la pantalla queda dibujada. Es decir, hasta que Streamlit
termina la ejecución y el DOM lleva 400 ms sin cambios. Se toma la mediana de varias repeticiones; la primera
visita a cada página se descarta.

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

### Qué se ha cambiado

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
