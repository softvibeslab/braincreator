# Skool Guide

Backend Hermes de Skool Agency Brain, rama `agentcalling`. Ofrece orientación, recursos con procedencia y un plan de tres mini misiones que el usuario debe confirmar. El modelo redacta y recomienda; la aplicación valida las fuentes, activa el plan y registra el progreso.

Esta guía describe la implementación. El [informe de verificación](../../docs/verification/agentcalling-coaching.md) distingue pruebas automatizadas, staging con Hermes real y recorridos de producción. Queda pendiente completar la creación de un plan en la interfaz de producción por créditos insuficientes del proveedor. El [plan de coaching](../../docs/plans/agentcalling-coaching.md) conserva los criterios de aceptación.

## Flujo de orientación

Una consulta normal ejecuta dos pasos: Hermes interpreta el propósito sobre el catálogo de lecciones; después se recuperan notas y segmentos mediante BM25 y Hermes prepara una respuesta fundamentada. No hay base vectorial. El nodo seleccionado y el historial reciente ayudan a interpretar respuestas breves. Los 62 nodos técnicos permanecen en el mapa, pero no se recuperan como contenido formativo.

La respuesta propone como máximo dos nodos y una pregunta breve con opciones. Cada recomendación requiere un ID real y evidencia del mismo nodo. Respuestas y tarjetas con tipos malformados se descartan; el texto del modelo no aporta URLs ni HTML ejecutable. SSE comunica estados de búsqueda y preparación; el texto aparece después de la validación, no token por token.

«Crear mi plan» genera un borrador de exactamente tres misiones de 5, 15 o 30 minutos por sesión, según la elección. Cada misión debe caber en ese tiempo, tener una sola acción, un entregable y un criterio observable. El servidor valida estructura, tiempos y nodos de apoyo. Todo el turno comparte un presupuesto de **una sola reparación**: puede corregir JSON de interpretación, una respuesta de orientación incompleta o un borrador inválido. Si ya se usó o la reparación falla, conserva el progreso anterior y devuelve un error recuperable. La estimación de esfuerzo se guía mediante instrucciones; no equivale a medir cuánto tardará cada persona.

El borrador no sustituye un plan activo hasta que el usuario confirma su ID. Descartarlo mantiene el plan anterior. Se puede guardar texto de avance, bloquear o retomar una misión y pausar el plan. El texto aún no guardado de una misión se conserva en memoria al cambiar de vista; hay que pulsar «Guardar avance» o una acción de misión para persistirlo antes de recargar. Marcar una misión como hecha almacena `completion_kind: "self_reported"`; no acredita una revisión automática ni un resultado comercial. Los ejercicios tienen `created_by: "Skool Guide"`, separados del material original del curso.

## Contratos HTTP

`server.py` escucha en `127.0.0.1:4651`; Nginx sirve HTTPS en `https://brainskool-api.softvibes.art`. El origen autorizado es `GUIDE_ORIGIN`. El cliente usa `credentials: "include"`; salvo `/health`, los endpoints requieren el encabezado `Origin` exacto. El cuerpo JSON de POST admite hasta 8192 bytes. La API nunca acepta un estado completo arbitrario del cliente.

| Endpoint | Entrada | Salida |
|---|---|---|
| `GET /health` | Sin sesión | `status`, `library_version`, `nodes`, `coaching` |
| `GET /state` | Cookie de sesión, si existe | `history`, `journey`, `saved_nodes`, `library_version`; crea o renueva la cookie |
| `GET /resources?node_id=…` | ID real del catálogo | Ficha con resumen, ideas, enlaces y tiempos; 404 si no existe |
| `POST /chat` | `message`, `node_id` opcional | SSE `status`, seguido de `result` o `error` |
| `POST /chat` | Los anteriores más `action: "generate_plan"`, `minutes: 5\|15\|30` | Mismo transporte, con borrador en `journey.draft` |
| `POST /journey` | Acción explícita y sus campos | Estado actualizado: `history`, `journey`, `saved_nodes` |

Ejemplo del resultado de chat, sin contenido del curso:

```json
{
  "answer": "Respuesta breve y fundamentada.",
  "question": {"text": "¿Qué te frena más?", "options": ["Poco volumen", "Poca calidad"]},
  "recommendations": [{
    "node_id": "ID_VALIDO", "title": "Título del catálogo", "category": "marketing",
    "reason": "Por qué encaja con el propósito.",
    "evidence": [{"source": "Fuente", "timestamp": "0:03:30", "evidence_id": "ID_RECUPERADO"}],
    "resources": []
  }],
  "library_version": "HASH_DEL_GRAFO",
  "journey": {}, "saved_nodes": []
}
```

`question` puede ser `null`. `journey` usa este esquema; las fases son `explore`, `draft`, `active`, `paused` o `completed`:

```json
{
  "goal": "Propósito confirmado o propuesto",
  "minutes": 15,
  "phase": "explore",
  "draft": null,
  "plan": null
}
```

Un borrador contiene `id`, `goal`, `minutes`, `created_at` y tres `missions`. Al confirmarse, el plan añade un nuevo `id`, `draft_id`, `status` y `confirmed_at`. Las misiones contienen `id`, `title`, `action`, `deliverable`, `done_when`, `minutes`, `node_ids`, `status`, `artifact`, `created_by`, `completion_kind`, `completed_at` y `updated_at`. Sus estados son `pending`, `active`, `blocked` o `completed`.

Acciones aceptadas por `/journey`:

| `action` | Campos adicionales | Efecto |
|---|---|---|
| `confirm_plan` | `draft_id` | Activa el borrador vigente y su primera misión; reemplaza el plan anterior |
| `discard_draft` | `draft_id` recomendado | Elimina la propuesta; conserva el plan previo |
| `mission_update` | `mission_id`, `status: active\|blocked\|completed`, `artifact` opcional | Guarda avance o estado; `artifact` admite hasta 3000 caracteres |
| `pause` / `resume` | Ninguno | Pausa o retoma el plan; no aplica a uno ya completado |
| `save_node` / `remove_saved_node` | `node_id` | Guarda o quita un nodo real, con máximo 50 guardados |
| `reset` | Ninguno | Vacía conversación, borrador, plan y nodos guardados de esta sesión |

La interfaz pide confirmación antes de `reset`. Identificadores de borrador obsoletos se rechazan, para impedir que otra pestaña confirme una propuesta que ya cambió. Las operaciones del mismo usuario se serializan y SQLite actualiza el estado en una transacción.

## Recursos originales

`ResourceCatalogue(library).get(node_id)` obtiene los enlaces de la nota y de `data/resources.json`, nunca de la respuesta del modelo. La ficha devuelve:

```json
{
  "node_id": "ID_VALIDO", "title": "Título", "summary": "Resumen de la fuente",
  "highlights": ["Primera idea", "Segunda idea", "Tercera idea"],
  "resources": [{
    "type": "skool", "title": "Abrir lección en Skool", "url": "https://www.skool.com/…/classroom/…",
    "origin": "original", "provenance": {"source": "node-note", "label": "Ficha del nodo"},
    "access_note": "Puede requerir acceso a la comunidad de Skool."
  }],
  "timestamps": [{"time": "0:03:30", "label": "Tema del fragmento"}],
  "notice": "No hay una plantilla descargable enlazada en esta ficha."
}
```

Tipos: `skool`, `youtube`, `template` o `link` —este último incluye Loom—. Solo se aceptan URLs públicas HTTPS sin credenciales ni tokens; se excluyen streams firmados y el VSL promocional. YouTube requiere un enlace de vídeo real. Un timestamp añade `url` únicamente si el exportador ha asociado directamente ese vídeo con la lección; no basta con mencionar un enlace en una nota. Los enlaces se deduplican. La interfaz presenta ideas clave o, en su ausencia, el resumen, para evitar repetir la misma información. Su procedencia queda validada contra los archivos, pero no se afirma disponibilidad externa en vivo.

La exportación local actual identifica 47 lecciones con Skool, 40 vídeos de YouTube, 3 de Loom y 1 documento de plantilla. Esos recursos se vinculan a 434 nodos de lección o concepto mediante su fuente exacta. No se inventan archivos para lecciones cuyo título menciona una plantilla.

Construcción, desde la raíz del repositorio:

```sh
npm ci --prefix apps/brainview
node scripts/build-hosting.mjs /ruta/a/exportacion-aprobada
python3 scripts/export-resources.py --source /ruta/a/elite-digital --hosting ./hosting
python3 -m unittest discover -s tests -v
```

Ejecutar el exportador **después del build**. Lee `index.json`, `videos.json`, el catálogo y las páginas originales sin modificarlos. `hosting/data/resources.json` y toda la biblioteca están ignorados por Git. Publicar esos datos tanto con el sitio estático como dentro de `BRAIN_LIBRARY`, conservando el mismo grafo e IDs en ambos lugares. Reiniciar el servicio para cargar una nueva versión del catálogo.

## Persistencia y privacidad

`JourneyStore` conserva las últimas 20 entradas de conversación, el borrador, el plan, sus entregables y los nodos guardados. El modelo recibe el contexto reciente y el plan; cada proceso Hermes está aislado, sin herramientas generales ni memoria de otros perfiles. El worker falla si aparecen herramientas inesperadas.

La cookie aleatoria es `HttpOnly; Secure; SameSite=Strict`, dura 30 días y se renueva al consultar estado o realizar acciones de chat/progreso. SQLite guarda el hash SHA-256 de su identificador, no la cookie. Cada lectura o actualización del estado renueva una retención de 30 días desde esa actividad. Los registros vencidos se purgan al procesar la siguiente operación de estado; no existe un trabajo independiente de borrado.

No hay cuentas, sincronización entre dispositivos ni recuperación de una sesión cuya cookie se perdió. Borrar cookies puede dejar datos inaccesibles hasta su vencimiento; «Borrar mi progreso» vacía el estado vigente. Una copia operativa de seguridad puede contener datos anteriores y debe seguir su propia política de retención. No se envían correos, mensajes ni recordatorios fuera de la aplicación.

## Configuración y límites

Archivo de configuración privado, modo `0600`, fuera del repositorio:

```ini
OPENROUTER_API_KEY=...
HERMES_HOME=/var/lib/skool-guide/.hermes
HERMES_PYTHON=/usr/local/lib/hermes-agent/venv/bin/python
HERMES_RUNTIME=/usr/local/lib/hermes-agent
BRAIN_LIBRARY=/var/lib/skool-guide/library
GUIDE_MODEL=openai/gpt-4.1-mini
GUIDE_ORIGIN=https://brainskool.softvibes.art
GUIDE_JOURNEY_DB=/var/lib/skool-guide/journey.sqlite
GUIDE_BUDGET_DB=/var/lib/skool-guide/budget.sqlite
PORT=4651
```

El modelo es configurable. Servicio `skool-guide.service`, usuario sin privilegios `skoolguide`, con escritura limitada a `/var/lib/skool-guide`. El servicio escucha solo en loopback; el proxy debe fijar `X-Real-IP` desde la conexión real. Ninguna clave del proveedor llega al navegador.

| Límite | Alcance |
|---|---|
| 200 solicitudes de chat/día | Global; cuota persistida en SQLite |
| 5 solicitudes de chat/minuto | Por IP |
| 2 consultas de modelo simultáneas | Global |
| 45 solicitudes de escritura/minuto | Por IP, compartidas entre `/chat` y `/journey` |
| 1 acción simultánea por sesión | Una segunda recibe 409 y puede reintentarse |
| 2000 caracteres por mensaje | Además del límite de cuerpo HTTP de 8 KiB |
| 60 segundos por paso Hermes | Interpretación + respuesta/borrador, con una reparación compartida por todo el turno |

La cuota mide solicitudes de chat, no invocaciones internas ni dinero gastado. El máximo es tres workers de 60 segundos: hasta 180 segundos de ejecución Hermes, más el procesamiento local, por debajo del plazo de 200 segundos del cliente. Nginx permite 200 segundos de lectura. Cuando el modelo o la red fallan, el mapa continúa disponible y el progreso ya persistido se conserva.

Un fallo de créditos o facturación del proveedor se clasifica como `ProviderBillingError`. No consume un reintento de reparación de JSON: la petición termina con un mensaje recuperable que conserva acceso al mapa, recursos y progreso. La operación debe restablecer la disponibilidad de la cuenta del proveedor antes de volver a generar respuestas; no se muestran saldos ni detalles de credenciales en la interfaz.

## Actualización, copias y rollback

Antes de desplegar, guardar juntos el frontend anterior, código del servicio, configuración, versión de biblioteca y copias consistentes de `journey.sqlite` y `budget.sqlite`. Los respaldos contienen información de usuarios: mantenerlos fuera de Git y del directorio público, con permisos limitados y una retención definida.

SQLite usa WAL. **No copiar únicamente el archivo `.sqlite` de un servicio activo**, porque podría omitir cambios presentes en el WAL. Usar la API de backup de SQLite o el comando `.backup`, ejecutado por una cuenta con los permisos adecuados:

```sh
sqlite3 /var/lib/skool-guide/journey.sqlite ".backup '/ruta/privada/backup/journey.sqlite'"
sqlite3 /var/lib/skool-guide/budget.sqlite ".backup '/ruta/privada/backup/budget.sqlite'"
sqlite3 /ruta/privada/backup/journey.sqlite 'PRAGMA integrity_check;'
```

Para una instantánea coordinada de ambos archivos, detener brevemente el servicio antes de respaldarlos. Registrar qué commit y versión del grafo corresponden a la copia.

Rollback de frontend: restaurar la versión anterior completa con sus assets y datos compatibles. Rollback de backend: detener `skool-guide`, restaurar código y biblioteca compatibles y conservar las bases actuales si el esquema lo permite. Si hace falta restaurar datos, mantener el servicio detenido y usar el mecanismo de backup/restauración de SQLite; no mezclar una base restaurada con archivos WAL/SHM de otra versión. Comprobar integridad y permisos antes de reiniciar. Restaurar un respaldo descarta los avances posteriores a esa copia: no hacerlo como parte automática de todo rollback de código.

Tras actualizar o revertir, comprobar `/health`, versión del grafo, `/state`, recursos de un nodo real y persistencia después de reiniciar. Detener únicamente el agente no debe afectar al mapa estático. Registrar por separado las pruebas de integración reales y de navegador realizadas en el entorno desplegado.
