# ADR-002 - OpenAI Vector Store como base de conocimiento de Marta Estetica

## Estado

Aceptada como arquitectura actual; requiere saneamiento y versionado.

## Contexto

El agente de DMs responde preguntas de clientes sobre tratamientos, precios, contacto y recomendaciones. Para evitar respuestas inventadas, la llamada a OpenAI Responses API usa File Search contra un Vector Store dedicado a Marta.

La auditoria confirmo un Vector Store llamado `Marta Sune ClonIA (Estilista)`, estado `completed`, con 11 archivos cargados y sin fallos de indexacion.

## Decision

Usar OpenAI Vector Store como base de conocimiento activa para el agente de DMs de Marta Estetica.

No usar todavia multiples bases de conocimiento ni metadata de filtro hasta completar saneamiento documental.

## Razones

- Ya esta integrado en produccion.
- La Responses API puede consultar File Search directamente.
- Es suficiente para el caso actual de una sola cuenta de Marta.
- Permite mantener informacion del centro separada del prompt base.

## Consecuencias

- La calidad de respuesta depende de la calidad, vigencia y consistencia de los documentos cargados.
- Sin metadata de version, el agente no puede distinguir fuente vigente de fuente antigua.
- Sin filtros por proyecto/perfil, no esta preparado para varios clientes o lineas de negocio.
- El solapamiento entre `botox_capilar.md` y `Tratamiento Botox.pdf` debe resolverse antes de modificar el Vector Store.

## Alternativas descartadas

- Responder solo desde prompt: demasiado fragil para precios y tratamientos.
- Hardcodear todos los datos en codigo: dificil de mantener y revisar con Marta.
- CRM o CMS completo en esta fase: excesivo antes de sanear fuentes y versionado.
- Crear nuevos Vector Stores ahora: no autorizado en esta fase y aumentaria la confusion.

## Fecha

2026-06-19
