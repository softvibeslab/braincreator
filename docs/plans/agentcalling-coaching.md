# Agentcalling — guía, recursos y mini misiones

Fecha: 2026-10-01. Rama: `agentcalling`. Evolución aprobada de Skool Guide para ayudar a pasar del contenido a una acción pequeña y retomable. Este documento describe el alcance implementado y los criterios de aceptación. El [informe de verificación](../verification/agentcalling-coaching.md) registra qué se comprobó en cada entorno y qué queda pendiente.

El [plan original de Brainview](brainview-hermes.md) permanece como histórico. Sus exclusiones de seguimiento persistente y los informes de esa versión no describen el alcance de esta evolución.

## Recorrido del usuario

**Propósito → pregunta clave → nodo y recursos → claridad → borrador → confirmación → mini misión → revisión.**

El popup mantiene tres vistas. **Conversación** aclara el objetivo mediante respuestas breves y una pregunta cada vez; **Mi camino** muestra el propósito, la siguiente misión y el recorrido; **Recursos** reúne lecciones guardadas y sus materiales disponibles. En móvil el panel ocupa casi toda la pantalla y el trabajo extenso puede ampliarse.

La guía no exige un cuestionario fijo. Debe aprovechar lo que el usuario ya explicó, ofrecer una recomendación útil con información parcial y evitar repetir preguntas. Ofrece un nodo principal y, como máximo, otro complementario, con el motivo de su relevancia. «Ir al nodo» oculta el popup, hace visible y enfoca el nodo y conserva la conversación para continuar.

## Recursos con procedencia

Una ficha ofrece hasta tres ideas clave o un resumen cuando no hay ideas separadas, enlaces originales disponibles y marcas de tiempo. No repite resumen e ideas si contienen lo mismo. Los materiales externos abren otra pestaña. Las fuentes aprobadas determinan qué puede mostrarse: Skool, vídeo de YouTube o Loom y documentos realmente enlazados. Las marcas de tiempo se enlazan a YouTube únicamente cuando existe una asociación directa entre el vídeo y la lección.

El catálogo actual de fuentes incluye 47 lecciones con Skool, 40 con YouTube, 3 con Loom y 1 documento de plantilla, reutilizados en 434 nodos vinculados a esas mismas fuentes. Esto prueba la existencia del enlace en el archivo original, no que su destino siga accesible. Skool y algunos documentos pueden exigir acceso.

Una lección titulada «plantilla» no implica que exista un descargable. La interfaz distingue **material original** de **ejercicio creado por Skool Guide**. El catálogo elimina enlaces promocionales, URLs inseguras y streams firmados; las respuestas del modelo no crean URLs.

## Plan confirmado y seguimiento

1. El usuario solicita preparar su plan y elige 5, 15 o 30 minutos por sesión.
2. Hermes propone exactamente tres mini misiones distintas, ajustadas a ese tiempo. Cada una incluye acción, entregable pequeño, criterio para terminar y nodos de apoyo con evidencia.
3. La aplicación guarda un borrador. El usuario puede revisarlo, pedir ajustes, generar otra propuesta o descartarlo.
4. Solo «Confirmar y guardar mi plan» activa el borrador vigente. Si había otro plan, la interfaz indica que será reemplazado; descartar el borrador conserva el anterior.
5. Se destaca una misión activa. Se puede escribir y guardar avance, marcar «Me atasqué», pedir un ejemplo o una acción menor, y pausar o retomar el plan. El texto no guardado se mantiene en memoria al cambiar de vista; debe guardarse para recuperarlo tras recargar.
6. «Ya lo hice» registra una finalización declarada por el usuario y prepara la siguiente misión pendiente. El progreso expresa acciones realizadas, no resultados comerciales ni entregables automáticamente revisados.
7. Al terminar, el usuario puede revisar lo conseguido y solicitar sus siguientes tres pasos.

Para sesiones de cinco minutos, las instrucciones piden microentregables realizables dentro del chat y sin gasto: escribir un criterio, una pregunta o un mensaje. El servidor comprueba tiempos, estructura y correspondencia de nodos. Una sola reparación se comparte entre interpretación, respuesta y borrador a lo largo de todo el turno. La duración de las misiones sigue siendo una estimación, cuya calidad debe evaluarse con casos reales.

## Estado persistente y control del usuario

Una cookie segura identifica una sesión anónima de este navegador. SQLite conserva las últimas 20 entradas de conversación, plan, borrador, entregables y hasta 50 nodos guardados, con caducidad de 30 días renovada al consultar o modificar estado. Reiniciar el servicio no debe perder ese avance. La aplicación ofrece borrar el progreso con confirmación.

No se implementan cuentas, recuperación tras perder la cookie, sincronización entre dispositivos ni recordatorios externos. El usuario debe conocer que borrar cookies o cambiar de navegador puede impedirle recuperar su sesión. Los registros vencidos se eliminan al procesar la siguiente operación de estado.

## Componentes y contratos

| Componente | Responsabilidad |
|---|---|
| `apps/brainview/src/guide.js` | Conversación, camino, recursos, accesibilidad y navegación al nodo |
| `services/skool-guide/coaching.py` | Instrucciones de orientación, preguntas y borradores |
| `retrieval.py` | Búsqueda BM25 y validación de recomendaciones contra evidencias |
| `resources.py` | Fichas y enlaces obtenidos exclusivamente de las fuentes |
| `journey.py` | Transacciones de estado, confirmación, progreso y retención |
| `server.py` | Frontera HTTP, sesión, validación, cuotas y ejecución Hermes |
| `scripts/export-resources.py` | Enriquecimiento privado tras construir el hosting |

Contratos públicos: `GET /state` recupera el avance; `GET /resources?node_id=…` entrega la ficha; `POST /chat` orienta o genera un borrador vía SSE; `POST /journey` aplica acciones explícitas. La aplicación controla IDs y estados. Hermes no puede declarar guardado, activar planes ni completar misiones mediante su texto. El [README del servicio](../../services/skool-guide/README.md) especifica campos y errores.

Cuotas: 200 solicitudes de chat globales al día, 5 por IP/minuto, 2 consultas de modelo simultáneas y 45 escrituras por IP/minuto. Cada paso Hermes tiene 60 segundos; todo el turno comparte una reparación como máximo. Son hasta tres workers y 180 segundos de ejecución Hermes, dentro del plazo de 200 segundos del cliente. Estos límites controlan solicitudes y concurrencia, sin prometer un gasto monetario exacto.

## Preparación y despliegue

Construir el frontend con la exportación aprobada y ejecutar después `scripts/export-resources.py --source … --hosting ./hosting`. Publicar `hosting/data/resources.json` junto al grafo, notas y transcripciones, y cargar esa misma versión en `BRAIN_LIBRARY`. Los datos del curso y de usuarios no se agregan al repositorio público.

Antes de actualizar el servicio, respaldar código, frontend, biblioteca y las bases SQLite mediante un backup consistente con WAL. Mantener progreso actual en un rollback de código compatible. Restaurar datos únicamente si es necesario y con el servicio detenido: una restauración descarta avances posteriores al respaldo. La guía del servicio detalla el procedimiento.

## Criterios de aceptación

- Pregunta sobre leads: explicación breve, una pregunta útil, recomendación fundamentada y ficha con Skool y el vídeo correcto; sin plantilla inventada.
- «Ir al nodo»: cierra el chat, enfoca el ID exacto con filtros o demo activos y permite retomar la conversación.
- Borrador: tres misiones pequeñas, ajustadas a 5/15/30 minutos, sin activación antes de confirmar. Descartar una propuesta conserva el plan previo.
- Seguimiento: guardar un entregable, recargar, reiniciar el servicio y recuperar el mismo estado; probar pausa, bloqueo, reanudación y avance a la misión siguiente.
- Etiquetas: finalización declarada por el usuario y ejercicios creados por Skool Guide distinguibles de los materiales originales.
- Sesiones: dos navegadores no comparten progreso; reset solo limpia el de la sesión solicitante; retención y rechazo de IDs obsoletos cubiertos por pruebas.
- Errores: caída del modelo, SSE interrumpido y recursos no disponibles permiten reintentar sin impedir usar el cerebro.
- Interfaz: recorrido con teclado, Escape, foco, panel ampliado y móvil; estados de carga legibles y una acción principal por momento.
- Seguridad y operación: tipos de JSON malformados, URLs inseguras, IDs/citas inventados, origen no permitido, cuotas y restauración de una copia coherente.

Las pruebas automatizadas, las pruebas locales con simulación y las consultas con Hermes real deben registrarse separadamente. Solo las comprobaciones hechas contra el entorno publicado cuentan como verificación de producción.

Estado de entrega: se comprobaron orientación, recursos, navegación, guardados y uso móvil en producción. También se recuperaron la conversación y el recurso guardado al reiniciar la API y recargar la web. El ciclo de borrador, confirmación, misión y restauración pasó en staging con Hermes real. Las 42 pruebas automatizadas pasan. Falta finalizar ese ciclo de plan en la interfaz de producción: la cuenta del proveedor devolvió créditos insuficientes. El fallo se maneja como disponibilidad del proveedor, sin repetir la generación ni perder progreso.
