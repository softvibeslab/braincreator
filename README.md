# Braincreator — Brainview

Integración de un agente Hermes con un cerebro 3D navegable. Rama de trabajo: `brainview`.

- [Plan aprobado](docs/plans/brainview-hermes.md).
- `apps/brainview/`: base del renderizador 3D actualmente utilizado por Skool Agency Brain.
- Sitio actual: https://brainskool.softvibes.art.

La biblioteca del curso, credenciales y datos de usuarios se mantienen fuera de este repositorio público. La implementación del agente está en esta rama.

## Agente implementado

- `apps/brainview/src/guide.js`: botón flotante, popup, sesión de chat y tarjetas «Ir al nodo».
- `services/skool-guide/`: servicio Hermes, recuperación de evidencia, validación y configuración de despliegue.
- `scripts/build-hosting.mjs`: construye el sitio a partir de una exportación aprobada fuera de Git.
- `tests/`: pruebas de recuperación y rechazo de IDs/citas inventados.

[Operación y límites](services/skool-guide/README.md).
