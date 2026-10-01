# Verificación Brainview

Fecha: 2026-10-01. Entorno: https://brainskool.softvibes.art y servicio dedicado en https://brainskool-api.softvibes.art.

## Resultados comprobados

- Plan y base del renderizador guardados primero en `brainview`, commit `5ca61be`, antes de implementar.
- Runtime Hermes real responde desde un usuario independiente del VPS. El worker rechaza cualquier herramienta habilitada inesperadamente.
- Consulta sobre leads: recomendación del nodo `marketing:a250e0fb7aed` con evidencia del curso.
- Consulta sobre ofertas para clínicas dentales: recomendó lección de ofertas y caso relacionado, con IDs y evidencia válidos.
- Flujo navegador en producción: botón flotante → popup → consulta → respuesta → tarjeta «Ir al nodo» → popup oculto → ficha «Cómo Atraer Leads Con Alta Intención De Compra» abierta → URL exacta `?node=marketing%3Aa250e0fb7aed`.
- Reabrir popup conserva conversación y muestra el nodo seleccionado como contexto.
- Sin errores de consola en el recorrido principal.
- API con TLS válido; origen no autorizado devuelve 403; mensaje vacío devuelve 400.
- Tres pruebas automatizadas aprobadas: búsqueda con acentos, rechazo de nodos/citas inexistentes y rechazo de rutas fuera de la biblioteca.
- Assets versionados por hash para evitar que el navegador reutilice JavaScript anterior al despliegue.

## Límites de esta entrega

- La adaptación móvil está implementada en CSS, pero no se pudo verificar visualmente: la herramienta solicitó 390×844 y el navegador mantuvo 1600×692.
- El chat comunica estados reales por SSE; el texto final aparece después de validar la respuesta, no token por token.
- Historial conservado al cerrar popup; no se conserva en la interfaz al recargar la página. Sesiones del servidor en memoria con caducidad de dos horas.
- Evaluación inicial con leads y oferta; no constituye una evaluación exhaustiva de todas las preguntas del curso.
- Cuota inicial de 200 consultas globales/día, 5 por IP/minuto y 2 simultáneas. Es un límite de uso, no una garantía de coste monetario.

## Mejora de legibilidad

Respuestas Markdown saneadas con títulos, negritas y listas; sin HTML ni enlaces arbitrarios del modelo. Instrucción de respuestas breves con idea principal, pasos separados y una acción siguiente. Tipografía de 15 px, mayor interlineado, panel más ancho y fuentes de tarjetas sin títulos repetidos. La lectura comienza en el inicio de la nueva respuesta.
