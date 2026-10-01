# Braincreator — Skool Agency Brain

Cerebro 3D navegable con Skool Guide, un acompañante Hermes para aclarar un propósito, encontrar conocimiento útil y aplicarlo mediante tres mini misiones. Rama de trabajo: `agentcalling`. Sitio: https://brainskool.softvibes.art.

## Experiencia implementada

El botón flotante abre tres vistas: **Conversación**, **Mi camino** y **Recursos**. El agente responde de forma breve, hace como máximo una pregunta clave por turno y ofrece un nodo principal y, cuando ayuda, uno complementario. «Ir al nodo» cierra el popup, enfoca el contenido y permite retomar la conversación.

Las fichas muestran hasta tres ideas clave —o un resumen cuando no hay ideas separadas—, enlaces originales disponibles y fragmentos con marcas de tiempo. Skool, YouTube, Loom y documentos se obtienen de las fuentes; el modelo no inventa enlaces. Los ejercicios creados por Skool Guide se distinguen del material original.

Cuando el usuario tiene claridad, elige sesiones de 5, 15 o 30 minutos y solicita un **borrador**. Puede revisarlo, ajustarlo o descartarlo; solo «Confirmar y guardar mi plan» lo activa. Cada misión tiene una acción, un entregable pequeño y un criterio de finalización. Se puede guardar un avance, pedir ayuda ante un bloqueo, pausar y continuar. «Ya lo hice» registra una confirmación del usuario, sin presentar el entregable como verificado automáticamente.

Conversación, plan y hasta 50 nodos guardados persisten en SQLite durante 30 días desde la última actividad de la sesión. Una cookie segura identifica este navegador. No hay cuentas, recuperación de acceso al borrar cookies ni sincronización entre dispositivos. Tampoco se envían recordatorios fuera de la aplicación.

## Código y documentación

- [Plan de esta evolución y criterios de aceptación](docs/plans/agentcalling-coaching.md).
- [Verificación de la entrega y comprobación pendiente](docs/verification/agentcalling-coaching.md).
- [Contratos de API, operación, límites y recuperación](services/skool-guide/README.md).
- [Plan original de Brainview](docs/plans/brainview-hermes.md), conservado como histórico.
- `apps/brainview/`: renderizador 3D; `src/guide.js` contiene la experiencia del agente.
- `services/skool-guide/`: Hermes, recuperación de evidencia, catálogo de recursos y estado de aprendizaje.
- `scripts/build-hosting.mjs` y `scripts/export-resources.py`: preparación del sitio y de los recursos privados.
- `tests/`: validación de evidencia, recursos, progreso y límites de la API.

La biblioteca del curso, credenciales, exportaciones de hosting y datos de usuarios quedan fuera de este repositorio público. La entrega cuenta con 42 pruebas automatizadas aprobadas, integración con Hermes real en staging y recorridos de producción en escritorio y móvil, incluida recuperación de conversación y recursos tras reiniciar la API y recargar. Queda pendiente completar el recorrido de creación de plan en la interfaz de producción por créditos insuficientes del proveedor; el informe de verificación distingue cada entorno. Los informes históricos no prueban esta versión.

## Preparación local

```sh
python3 -m unittest discover -s tests -v
npm ci --prefix apps/brainview
node scripts/build-hosting.mjs /ruta/a/exportacion-aprobada
python3 scripts/export-resources.py --source /ruta/a/elite-digital --hosting ./hosting
```

La última instrucción debe ejecutarse después del build. Genera `hosting/data/resources.json` a partir de las fuentes aprobadas, sin modificarlas. Todo `hosting/` está ignorado por Git. Publicar el frontend, grafo y catálogo de recursos de la misma versión; consultar la guía de operación antes de actualizar el servicio persistente.
