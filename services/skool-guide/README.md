# Skool Guide

Backend dedicado de Hermes para Brainview. `server.py` escucha en loopback; Nginx publica solo `/chat` y `/health` sobre HTTPS.

Dos pasos de Hermes por consulta: interpretación semántica sobre el catálogo de lecciones, seguida de búsqueda BM25 sobre notas y segmentos de transcripción; respuesta fundamentada y recomendaciones validadas contra las evidencias recuperadas. No utiliza una base vectorial. El modelo actual es `openai/gpt-4.1-mini` mediante OpenRouter, ejecutado por el runtime Hermes instalado. Cada invocación usa un proceso separado, sin herramientas generales, memoria compartida ni contexto de otros perfiles. El worker falla si Hermes activa herramientas inesperadas.

Las fuentes se cargan de `BRAIN_LIBRARY`, una exportación privada que contiene `data/graph.json`, notas y transcripciones. Los 62 nodos técnicos se mantienen en el mapa pero no se usan como contenido formativo. Las recomendaciones requieren un ID válido y una evidencia del mismo nodo.

Configuración de servidor, fuera del repositorio, archivo modo 0600:

```
OPENROUTER_API_KEY=...
HERMES_HOME=/var/lib/skool-guide/.hermes
HERMES_PYTHON=/usr/local/lib/hermes-agent/venv/bin/python
HERMES_RUNTIME=/usr/local/lib/hermes-agent
BRAIN_LIBRARY=/var/lib/skool-guide/library
GUIDE_MODEL=openai/gpt-4.1-mini
GUIDE_ORIGIN=https://brainskool.softvibes.art
PORT=4651
```

Servicio: `skool-guide.service`, usuario sin privilegios `skoolguide`. API: `https://brainskool-api.softvibes.art`. Certificado Let's Encrypt con renovación automática. Sin secretos en el navegador.

El chat mantiene un historial en memoria por cookie aleatoria HttpOnly/Secure/SameSite=Strict, durante dos horas de inactividad; se pierde al reiniciar el servicio. La interfaz conserva conversación al cerrar el popup, pero no al recargar la página. No hay cuentas ni seguimiento persistente de aprendizaje.

Límites iniciales: 200 consultas totales/día, 5 por IP/minuto, 2 consultas simultáneas, 2000 caracteres por mensaje y 90 segundos por paso Hermes. La cuota de consultas persiste en SQLite. No representa un límite monetario exacto del proveedor. La respuesta llega al finalizar la validación; SSE muestra estados reales de búsqueda y preparación, no token por token.

Pruebas: `python3 -m unittest discover -s tests -v` desde la raíz. Reconstrucción del frontend: `npm ci --prefix apps/brainview` y `node scripts/build-hosting.mjs /ruta/a/exportacion-aprobada`. Salida privada ignorada por Git: `hosting/`.

Rollback frontend: volver al ZIP anterior de Skool Agency Brain. Backend: detener `skool-guide` no afecta al mapa estático. Para actualizar fuentes, sustituir la exportación privada y reiniciar el servicio; publicar el mismo grafo con el frontend para conservar IDs compatibles.
