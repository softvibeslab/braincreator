# Verificación — Agentcalling coaching

Fecha: 2026-10-01. Rama: `agentcalling`. Sitio: https://brainskool.softvibes.art. API: https://brainskool-api.softvibes.art.

La entrega incorpora orientación con preguntas breves, recursos originales y mini misiones persistentes. Se verificaron componentes, integración Hermes real y recorridos del sitio publicado. **No se considera cerrado el recorrido completo de plan en la interfaz de producción**: la última comprobación quedó detenida por créditos insuficientes del proveedor.

## Pruebas automatizadas

**42 pruebas aprobadas**, incluida la regresión del fallo de créditos del proveedor. La ejecución completa terminó en aproximadamente 6,3 segundos, tratando `ResourceWarning` como error:

```sh
python3 -W error::ResourceWarning -m unittest discover -s tests -v
```

Cubren recuperación y validación de evidencia, respuesta malformada, URLs y recursos originales, estado persistente, confirmación de borradores, aislamiento de sesiones, acciones de progreso y fronteras HTTP. Los modelos simulados usados por pruebas unitarias no cuentan como validación de Hermes real.

El manejo específico de `ProviderBillingError` forma parte del conjunto aprobado: evita tratar un fallo de créditos como una respuesta JSON que debe repararse.

## Staging con Hermes real

Se comprobó mediante el servicio de staging:

- Dos turnos de orientación con respuestas reales del modelo.
- Generación de tres mini misiones para sesiones de cinco minutos.
- Borrador guardado sin activar el plan antes de la confirmación.
- Confirmación explícita y activación de la primera misión.
- Finalización declarada por el usuario y actualización del progreso.
- Restauración del estado persistido.
- Recursos originales de Skool y YouTube asociados a sus nodos.

Este recorrido valida la integración del servicio con Hermes y SQLite en staging. No sustituye la comprobación pendiente del flujo completo dentro de la interfaz publicada.

## Interfaz local con datos de prueba

Se comprobó el frontend final en `http://127.0.0.1:8877`, con datos expresamente rotulados como ficticios y **sin Hermes**. Este recorrido verifica la interacción y los estados de la interfaz; no cuenta como prueba de generación del modelo ni de producción.

- Un borrador permaneció sin activar hasta su confirmación explícita.
- Se escribió una nota de misión sin guardarla, se abrió y guardó un recurso y se volvió a la misión: el texto seguía igual en memoria.
- «Guardar avance» persistió la nota. «Me atasqué» mostró las tres opciones de ayuda y «Ya puedo continuar» retomó la misión.
- Completar la primera misión mostró «1 de 3», activó la siguiente y conservó la nota anterior en el recorrido completo.
- Pausar y recargar mantuvo tanto «1 de 3» como el estado de pausa. Retomar devolvió al usuario a la segunda misión.
- La flecha derecha del teclado cambió de «Mi camino» a «Recursos»; Escape cerró el popup.

## Producción: interfaz y recursos

Recorridos comprobados en escritorio y en móvil con viewport **390 × 844**, sin desbordamiento horizontal:

- Dos turnos reales de conversación y pregunta breve con botones de respuesta.
- Apertura de la ficha de recursos desde la recomendación.
- Enlaces de Skool, YouTube y fragmentos con marcas de tiempo del vídeo asignado a la lección.
- Guardado de un nodo en la vista Recursos.
- «Ir al nodo» cierra el popup y enfoca el nodo exacto.
- Reapertura del agente con el historial de la conversación disponible.
- Reinicio de la API seguido de recarga de la web: se recuperaron los dos turnos de conversación y el recurso guardado con su título correcto. Esta comprobación de persistencia no requiere una nueva generación del modelo.

La navegación comprobada corresponde a «Cómo Atraer Leads Con Alta Intención De Compra», ID `marketing:a250e0fb7aed`, y su URL `?node=marketing%3Aa250e0fb7aed`.

La comprobación de recursos valida su asociación con la fuente y las URLs presentadas. No acredita acceso de todos los visitantes a Skool o a documentos protegidos, ni disponibilidad perpetua de enlaces externos.

## Comprobación pendiente

Completar en la interfaz de producción: solicitar un borrador de tres misiones, confirmar el plan, guardar un entregable, marcar una misión como hecha y recuperar el avance al recargar.

El proveedor OpenRouter devolvió **402 por créditos insuficientes** durante esa prueba. La disponibilidad de la cuenta del proveedor debe restablecerse antes de repetirla. No se atribuye el bloqueo al estado guardado ni se declara aprobado el flujo completo por los resultados de staging.

El servicio distingue este caso con `ProviderBillingError` y evita reintentar como si fuera JSON inválido. Ofrece un mensaje recuperable: el guía no puede generar respuestas por el momento, pero el mapa, los recursos y el progreso permanecen disponibles. No expone el saldo ni detalles de la cuenta.

## Cierre de la verificación

Tras restablecer el proveedor, repetir únicamente el recorrido pendiente y las regresiones afectadas. Registrar el resultado real, el total actualizado de pruebas y el commit desplegado. Mantener separados los resultados de producción y de staging; no marcar esta entrega como verificada por completo mientras falte ese recorrido.
