# Fase 7 · Menos texto, más claridad

Regla: cada dato aparece en un solo sitio. Lo que explica (subtítulos, leyendas, notas metodológicas) pasa a un
tooltip ⓘ (`ui/components.tip`); lo que detalla, a la ventana de la alerta o a la ficha del proveedor.

| Página | Se queda | Pasa a tooltip (ⓘ) | Pasa a la ventana de detalle | Se elimina (repetido) |
|---|---|---|---|---|
| Centro de control | Título, banner (titular), 5 KPI (etiqueta y cifra), tarjeta = estado + proveedor y ciudad + margen, mapa, calendario de roturas, treemap | Fecha de los datos, subtítulos de tarjetas, texto de cada KPI, leyenda de marcadores, fiabilidad, nota del treemap | Evento, medicamento afectado, acciones creadas, historial de pedidos, noticia completa | Subtítulo del banner, cita en el detalle (ya está en la noticia), «Afecta a…» de cada tarjeta, pie de página |
| Calendario | Título, 4 KPI, calendario, semáforo (estado + 3 cifras) | Supuesto de la proyección, textos de KPI, subtítulo del semáforo, causa de cada estado | Fórmula de la fecha límite | Párrafos de «hoy es…», línea `why` de cada tarjeta |
| Proveedores | Título, buscador, 4 KPI, ranking (#, proveedor y ciudad, stock, índice), zonas, país, alternativos tardíos | Textos de KPI y de tarjetas | Material, alternativo, gasto y vulnerabilidad (ficha) | Columnas Material, Alternativo y Gasto del ranking; Gasto de países; columnas repetidas de alternativos |
| Simulador | Pregunta, ejemplo, formulario, resultado (KPI, tablas, mapa, plan) | Cómo funciona la IA, origen del escenario, textos de KPI y de tablas | — | Subtítulos de tarjetas, nota final del plan |
| Ventanas (alerta, ficha, día) | Estado, proveedor, impacto, plan, decisión, pedido y recordatorio | Fiabilidad, cálculo de la cantidad, historial sintético | Noticia original (plegada) | «Información» y «Decisión», cita, leyenda del calendario, notas |
| Transparencia | Igual, compacto | — | — | — |
