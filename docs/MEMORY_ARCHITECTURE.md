# Arquitectura de memoria conversacional

Fecha de referencia: 2026-06-19

## Arquitectura actual

```text
Instagram sender_id
-> dm_context.instagram_user_id
-> previous_response_id
-> OpenAI Responses API
-> nuevo response_id
-> PostgreSQL
```

## Flujo actual

1. Meta envia un DM al webhook `/webhook`.
2. `tools.dm_responder` extrae `sender.id` y texto del mensaje.
3. Si el mensaje parece una reserva, cambio o cancelacion, se deriva a WhatsApp sin consultar OpenAI.
4. Si no es reserva, se lee `dm_context.response_id` usando `sender.id` como `instagram_user_id`.
5. Si existe `response_id`, se envia a OpenAI como `previous_response_id`.
6. OpenAI genera respuesta usando Responses API y File Search.
7. Se guarda el nuevo `response_id` en PostgreSQL.
8. Se envia la respuesta al usuario por Instagram Graph API.

## Que se recuerda

PostgreSQL recuerda solo:

- `instagram_user_id`.
- `response_id`.
- `updated_at`.

El contenido conversacional real queda del lado de OpenAI, asociado al `previous_response_id`.

## Que no se recuerda localmente

No se guarda localmente:

- Mensajes privados completos de DMs.
- Resumen de conversacion.
- Ultima intencion.
- Tratamiento consultado.
- Servicio solicitado.
- Interes de reserva.
- Estado del lead.
- Derivacion a WhatsApp.
- Intervencion humana.
- Human handoff.
- Ultima fecha real de contacto como campo separado.
- Proyecto.
- Perfil.
- Canal.
- Cuenta de canal.
- `external_user_id` separado de la clave antigua.
- Base de conocimiento usada.

## Dependencias de OpenAI

La continuidad conversacional depende de que OpenAI siga reconociendo el `previous_response_id`.

Si OpenAI conserva el contexto remoto, el agente puede continuar la conversacion. Si OpenAI rechaza, pierde o expira ese contexto con un error especifico de `previous_response_id`, el fallback queda implementado localmente y pendiente de despliegue: se reintenta una sola vez sin contexto previo.

## Si se pierde la fila de PostgreSQL

Si se pierde una fila de `dm_context`, el sistema no encuentra `previous_response_id` y empieza una conversacion nueva. No hay resumen local para reconstruir el contexto.

## Si el contexto remoto deja de existir

Si OpenAI rechaza el `previous_response_id` con una senal estructurada de contexto invalido, la llamada normal se reintenta una sola vez sin `previous_response_id`. El reset se registra en logs como `context_reset`. Este cambio esta implementado localmente y pendiente de despliegue.

## Limitaciones para intervencion humana

Una persona humana no puede reconstruir desde PostgreSQL que queria el cliente, que tratamiento consulto o si fue derivado a WhatsApp. Para retomar casos, haria falta consultar Instagram, logs externos o el contexto remoto si todavia existe.

## Limitaciones para multiperfiles

La clave actual es solo `instagram_user_id`, que en la practica representa el usuario externo que escribe.

No hay aislamiento por:

- `project_id`.
- `profile_id`.
- `channel`.
- `channel_account_id`.
- `external_user_id`.
- `knowledge_base_id`.

Riesgo: si el mismo identificador externo aparece en otro contexto, o si el sistema se reutiliza para otra cuenta, podria reutilizarse un `previous_response_id` incorrecto o consultarse una base de conocimiento no adecuada.

## Estructura futura recomendada

Campos imprescindibles para la siguiente iteracion:

```text
project_id
profile_id
channel
channel_account_id
external_user_id
previous_response_id
knowledge_base_id
updated_at
```

Clave logica recomendada:

```text
(project_id, profile_id, channel, channel_account_id, external_user_id)
```

Campos posteriores recomendados:

```text
conversation_summary
last_intent
requested_service
lead_status
human_handoff
last_message_at
```

No implementar todavia la clave compuesta. El fallback de contexto invalido queda implementado localmente y pendiente de despliegue.

## Cambio A implementado localmente - fallback de previous_response_id invalido

Flujo implementado localmente:

```text
intento normal
-> error de contexto reconocido
-> retry una vez sin previous_response_id
-> guardar nuevo response_id
-> registrar context_reset en logs
```

Archivos afectados:

- `tools/dm_responder.py`: envuelve la llamada a Responses API y detecta errores de contexto.
- `tools/db_context.py`: sin cambios; se reutiliza `guardar_response_id`.
- Documentacion: actualizar este archivo y `docs/PROJECT_STATE.md`.

No hay migracion SQL ni cambios de esquema para este cambio.

Compatibilidad con registros existentes:

- Los 16 registros actuales seguirian siendo validos.
- El nuevo `response_id` reemplaza al anterior solo si el retry tiene exito.

Rollback:

- Revertir el cambio de codigo en `tools/dm_responder.py`.
- No hay rollback de esquema.

Pruebas locales:

- Simulan `previous_response_id` invalido.
- Verifican retry unico sin `previous_response_id`.
- Verifican que se guarda el nuevo `response_id`.
- Verifican que no se hace bucle infinito de retries.

Prueba controlada en produccion:

- Usar un usuario de prueba o conversacion controlada.
- Forzar un `response_id` invalido solo si se aprueba expresamente una manipulacion controlada de DB.
- Confirmar respuesta enviada y reset registrado.

Riesgos:

- Clasificar mal errores de OpenAI no relacionados con contexto.
- Ocultar incidentes reales si se reintenta demasiado.
- Perder continuidad en una conversacion antigua, aunque se preserve respuesta al cliente.

## Plan no ejecutado - Cambio B: migracion retrocompatible hacia clave compuesta

Campos objetivo:

```text
project_id
profile_id
channel
channel_account_id
external_user_id
```

Archivos afectados previstos:

- `tools/db_context.py`: lectura/escritura por clave compuesta y compatibilidad temporal con `instagram_user_id`.
- `tools/dm_responder.py`: pasar proyecto, perfil, canal y cuenta de canal al modulo de memoria.
- `config.py`: definir identificadores estables de proyecto/perfil/canal si no existen.
- `docs/MEMORY_ARCHITECTURE.md`: actualizar estado real tras implementacion.

Migracion SQL propuesta:

```sql
ALTER TABLE dm_context
ADD COLUMN project_id TEXT,
ADD COLUMN profile_id TEXT,
ADD COLUMN channel TEXT,
ADD COLUMN channel_account_id TEXT,
ADD COLUMN external_user_id TEXT,
ADD COLUMN knowledge_base_id TEXT;

UPDATE dm_context
SET project_id = 'marta-estetica',
    profile_id = 'martasunestilista',
    channel = 'instagram',
    channel_account_id = 'PENDIENTE_DE_VALIDACION',
    external_user_id = instagram_user_id,
    knowledge_base_id = 'PENDIENTE_DE_VALIDACION'
WHERE project_id IS NULL;

CREATE UNIQUE INDEX dm_context_conversation_key
ON dm_context (
    project_id,
    profile_id,
    channel,
    channel_account_id,
    external_user_id
);
```

Compatibilidad con los 16 registros existentes:

- `external_user_id` se rellenaria desde `instagram_user_id`.
- `instagram_user_id` podria mantenerse temporalmente para compatibilidad.
- El codigo nuevo podria leer primero por clave compuesta y, si no encuentra fila, migrar/usar la fila antigua.

Rollback:

```sql
DROP INDEX IF EXISTS dm_context_conversation_key;

ALTER TABLE dm_context
DROP COLUMN IF EXISTS project_id,
DROP COLUMN IF EXISTS profile_id,
DROP COLUMN IF EXISTS channel,
DROP COLUMN IF EXISTS channel_account_id,
DROP COLUMN IF EXISTS external_user_id,
DROP COLUMN IF EXISTS knowledge_base_id;
```

Pruebas locales:

- Crear tabla temporal con esquema actual.
- Insertar filas equivalentes a los 16 registros actuales.
- Ejecutar migracion.
- Verificar unicidad por clave compuesta.
- Verificar lectura/escritura por clave nueva.
- Verificar fallback a fila antigua durante transicion.

Prueba controlada en produccion:

- Hacer backup/export previo de `dm_context`.
- Ejecutar migracion en ventana controlada.
- Probar un DM informativo de bajo riesgo.
- Verificar que no se mezcla con otra cuenta.
- Verificar que el nuevo `response_id` queda asociado a la clave compuesta.

Riesgos:

- Valor incorrecto en `channel_account_id` podria provocar duplicados o mezcla.
- Un indice unico podria fallar si hay duplicados no detectados.
- Durante transicion, dos caminos de lectura podrian divergir si no se define prioridad clara.
- El despliegue debe coordinar migracion y codigo para evitar escrituras antiguas incompletas.
