# Brainview — agente Hermes para Skool Agency Brain

Estado: plan aprobado por el usuario y registrado antes de implementar en `softvibeslab/braincreator`, rama `brainview`.

## Objetivo

Integrar un experto conversacional que encuentre contenido útil, explique cómo aplicarlo y lleve al usuario directamente al nodo recomendado en https://brainskool.softvibes.art.

## Experiencia acordada

- Botón flotante inferior derecho: «Pregúntale al experto».
- Popup de chat adaptable a móvil, accesible por teclado y cerrable con Escape.
- Respuestas progresivas, estado de carga, errores recuperables y conversación conservada al cerrar.
- El nodo seleccionado se aporta como contexto para preguntas como «¿cómo aplico esto?».
- Cada respuesta puede incluir de uno a tres nodos con título, categoría, motivo de la recomendación y botón «Ir al nodo».
- Al pulsar el botón: ocultar chat, detener demo, habilitar categoría si estaba filtrada, enfocar/resaltar nodo, mostrar ficha y actualizar URL sin recargar.
- Al reabrir el chat, conservar historial y contexto del nodo visitado.

Caso de aceptación principal: «¿Cómo atraer leads?» recomienda, cuando corresponde a la intención de la consulta, «Cómo Atraer Leads Con Alta Intención De Compra», ID `marketing:a250e0fb7aed`, con enlace https://brainskool.softvibes.art/?node=marketing%3Aa250e0fb7aed.

## Base verificada

496 nodos, 809 relaciones, 10 categorías y 47 transcripciones. 27 vídeos tienen revisión visual cada 15 segundos; 20 lecciones solo cobertura textual.

El cliente existente reconoce `?node=`. `selectNode` detiene la demo, restaura visibilidad, resalta conexiones, abre la ficha, mueve la cámara y actualiza la URL. Exponer un contrato de navegación estable en vez de depender del objeto de depuración `window.__brain`.

## Implementación por fases

1. Crear rama brainview y registrar el plan y una base reproducible del código actual. Excluir credenciales, cookies, dependencias, vídeos y archivos temporales.
2. Crear perfil Hermes dedicado, independiente de otros agentes y memorias. Confirmar runtime, autenticación del proveedor e integración API soportada por la versión instalada.
3. Generar índice de notas y fragmentos de transcripciones. Conservar node_id, título, categoría, texto, fuente, tiempo y versión del grafo. Combinar búsqueda textual y semántica, usando vecindad del grafo para contexto. Actualizaciones incrementales y control de duplicados.
4. Implementar herramientas limitadas de lectura: buscar contenido, leer nodo y consultar conexiones. Validar recomendaciones contra el catálogo. No inventar IDs ni presentar inferencias como afirmaciones del curso.
5. Crear API intermediaria para chat, sesiones separadas, streaming, validación de tarjetas y manejo de errores. Credenciales solo en servidor; límites de solicitudes, concurrencia y presupuesto. No exponer panel administrativo ni herramientas generales de terminal.
6. Crear popup y tarjetas en el cliente. Recibir node_id estructurado y construir enlaces desde el catálogo validado; no ejecutar HTML o instrucciones arbitrarias del modelo.
7. Conectar «Ir al nodo» con la navegación del cerebro. Preservar conversación, foco accesible y estado de filtros. Comprobar comportamiento con Cinema y demo.
8. Evaluar con preguntas de marketing, oferta, ventas, contratación y operaciones. Verificar fundamentos de respuestas, pertinencia, enlaces, aislamiento de sesiones y errores. Usar el caso de leads como prueba explícita, sin forzar esa lección para todas las consultas.
9. Desplegar servicio Hermes dedicado en VPS y frontend en Hostinger, verificar HTTPS/CORS y comunicación extremo a extremo. Mantener versión previa para rollback. Si el agente no está disponible, el mapa sigue funcionando.

## Contrato de respuesta propuesto

Texto de respuesta más recomendaciones estructuradas: `{node_id, reason, evidence:[{source, timestamp}]}`. El servidor deriva título, categoría y URL del catálogo actual y rechaza IDs inexistentes. Las citas deben corresponder a fragmentos realmente recuperados.

## Criterios de finalización

- Chat funciona con Hermes real; ningún simulador se presenta como integración terminada.
- Recomendaciones válidas con fuentes verificables y respuesta honesta cuando no hay evidencia.
- Botón «Ir al nodo» oculta popup, enfoca el nodo exacto y conserva historial.
- Sesiones no comparten historial ni memoria personal.
- Interfaz comprobada en escritorio y móvil; errores, teclado, reconexión y límite de consumo cubiertos.
- Producción comprobada con HTTPS, consultas reales y navegación al nodo de leads.

## Fuera de la primera versión

Rutas de aprendizaje persistentes, cuentas de usuario y seguimiento de progreso quedan para una fase posterior.

## Referencia técnica

Hermes API Server: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server/
La disponibilidad de endpoints debe verificarse contra el runtime instalado antes de elegir el adaptador.
