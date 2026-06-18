# Estado del proyecto - Marta Sune

Fecha de referencia: 2026-06-19

## Cliente y proyecto

- Cliente: Marta Sune Estilista & Estetica Avanzada.
- Proyecto: `cevecom-marta-v2`.
- Objetivo operativo: automatizar contenidos de Instagram, respuestas a DMs y respuestas a comentarios para la cuenta de Marta.
- Cuenta validada: `martasunestilista`.

## Repositorio

- Repositorio: `CedricVz/cevecom-marta-v2`.
- Rama actual: `main`.
- Commit de partida de esta fase: `933623f`.
- Estado base: `HEAD` coincide con `origin/main` en `933623f` antes de esta fase documental.

## Arquitectura desplegada

```text
Meta / Instagram Webhooks
-> Railway
-> gunicorn
-> tools.dm_responder:app
-> PostgreSQL Railway
-> OpenAI Responses API
-> OpenAI File Search / Vector Store
-> Instagram Graph API
```

El endpoint principal de produccion es `/webhook`. El healthcheck de Railway usa `/healthz`.

## Modulos terminados

### Agente de DMs

- Activo en Railway.
- Recibe DMs desde Meta Webhooks.
- Usa OpenAI Responses API con `gpt-4o`.
- Usa File Search contra un Vector Store de Marta.
- Guarda continuidad conversacional en PostgreSQL mediante `previous_response_id`.
- Tiene regla determinista para derivar reservas, cambios y cancelaciones a WhatsApp.

### Comentarios de Instagram

- Desarrollados.
- Desplegados.
- Validados en produccion.
- Respuesta publica confirmada.
- Estado `published`.
- Anti-bucle confirmado con estado `ignored_own_account`.
- No requieren mas cambios.

## Modulos pendientes

### Videos

- Benchmark de seis piezas pendiente.
- No iniciar hasta cerrar la fase de memoria y conocimiento.
- No continuar regenerando la Fila 3 en esta fase.
- El modulo de videos mantiene decisiones abiertas sobre benchmark, assets, normalizacion y regeneracion.

### Memoria conversacional

- Pendiente fortalecer aislamiento por proyecto y perfil.
- Pendiente fallback si OpenAI rechaza un `previous_response_id`.
- Pendiente guardar resumen o estado conversacional local para continuidad humana.
- Fallback y clave compuesta estan planificados, no implementados.

### Base de conocimiento

- Pendiente saneamiento y versionado.
- Pendiente resolver posible solapamiento entre `botox_capilar.md` y `Tratamiento Botox.pdf`.
- Pendiente definir proceso formal de actualizacion.

## Servicios externos

- Railway: hosting del webhook y servicio PostgreSQL.
- PostgreSQL Railway: persistencia de contexto de DMs y eventos de comentarios.
- OpenAI: Responses API y Vector Store/File Search.
- Meta / Instagram Graph API: recepcion de webhooks y envio de respuestas.
- Google Sheets / Drive: pipeline de contenidos y calendario.
- HeyGen: generacion de videos.
- Gmail SMTP: emails operativos y notificaciones.

## Estado de Railway

- Produccion activa.
- Deploy automatico desde `main`.
- Web process definido en `Procfile`.
- Healthcheck configurado en `/healthz`.
- No se cambian variables ni deploys en esta fase.

## Estado de PostgreSQL

- Activo en Railway.
- Tabla de memoria de DMs: `dm_context`.
- Campos confirmados: `instagram_user_id`, `response_id`, `updated_at`.
- Registros auditados: 16.
- Registro mas antiguo auditado: `2026-05-15T21:55:23Z`.
- Registro mas reciente auditado: `2026-06-18T18:28:44Z`.
- No existe aislamiento por `project_id`, `profile_id`, `channel_account_id` o `knowledge_base_id`.
- No se modifica PostgreSQL en esta fase.

## Estado del Vector Store

- Nombre: `Marta Sune ClonIA (Estilista)`.
- Estado: `completed`.
- Creado aproximadamente: `2026-04-23T16:31:36Z`.
- Archivos indexados: 11.
- Archivos fallidos: 0.
- Tamaño indexado auditado: 37,331 bytes.
- No tiene metadatos de version o vigencia visibles.
- No se suben, eliminan ni sustituyen documentos en esta fase.

## Estado del modulo de DMs

- Correcto para el escenario actual de una sola cuenta de Marta Estetica.
- Usa `sender_id` de Instagram como clave de conversacion.
- Recupera `response_id` desde PostgreSQL y lo envia como `previous_response_id`.
- Guarda el nuevo `response_id` tras cada respuesta correcta.
- Si la consulta es de reserva, deriva a WhatsApp sin pasar por el modelo.
- Riesgo conocido: si OpenAI rechaza el contexto remoto, no hay fallback implementado.

## Estado del modulo de comentarios

- Cerrado y validado en produccion.
- Publicacion de respuesta confirmada.
- Persistencia en PostgreSQL confirmada.
- Anti-bucle confirmado.
- No requiere mas cambios salvo fallo nuevo reproducible.

## Estado del modulo de videos

- Pendiente benchmark de seis piezas.
- Benchmark no iniciado.
- Fila 3 pendiente de decision/regeneracion, pero no debe continuarse en esta fase.
- No iniciar hasta cerrar la fase de memoria y conocimiento.
- No ejecutar pipeline completo ni consumir creditos HeyGen durante esta fase.

## Riesgos conocidos

- Memoria local fragil: solo conserva puntero remoto.
- Dependencia de OpenAI para recuperar el contexto previo.
- Sin fallback ante `previous_response_id` invalido.
- Sin aislamiento por proyecto, perfil, canal o cuenta.
- Vector Store sin metadatos de version, propietario, vigencia o reemplazo.
- Posible solapamiento entre documentos de Botox.
- Documentacion tecnica historicamente dispersa entre `CLAUDE.md`, `docs/` y estado operativo.

## Siguiente bloque aprobado

Bloque aprobado actual: Fase 0, documentar arquitectura y preparar saneamiento de conocimiento.

No estan aprobados todavia:

- Cambios de codigo.
- Migraciones.
- Modificaciones de PostgreSQL.
- Cambios en Railway.
- Cambios en Vector Store.
- Benchmark de videos.
