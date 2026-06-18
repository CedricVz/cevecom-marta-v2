# Instagram public comments

Fecha: 2026-06-18

## Objetivo

Anadir soporte seguro para recibir comentarios publicos de Instagram y responder
solo cuando el caso sea sencillo y de bajo riesgo, sin alterar el agente actual
de DMs.

## Arquitectura

```text
Meta Webhooks POST /webhook
        |
        |-- entry.messaging[]  -> tools.dm_responder._procesar_dm()
        |
        `-- entry.changes[] where field="comments"
              -> tools.instagram_comments.procesar_comment_event()
              -> PostgreSQL instagram_comment_events
              -> Graph API POST /{ig-comment-id}/replies
                 (pendiente de validacion real con Meta)
```

El endpoint Flask sigue siendo `tools/dm_responder.py:/webhook`. La logica de
comentarios vive en `tools/instagram_comments.py` para no mezclarla con el
flujo de DMs.

## Webhook de Meta

Objeto de Webhooks previsto: Instagram.

Campos actuales del proyecto:

- `messages`: DMs, ya usado por el agente actual.
- `comments`: comentarios publicos, nuevo campo candidato a suscribir.

Antes de produccion hay que validar en Meta Developer, con la app y cuenta real:

- que el field de webhook para comentarios es `comments`;
- que la estructura exacta del payload coincide con lo esperado;
- que el comportamiento no cambia por tipo de cuenta, permisos o version de
  Graph API.

Payload esperado para comentarios, pendiente de validar con eventos reales:

- `entry[].changes[].field = "comments"`
- `entry[].changes[].value.id`: `comment_id`
- `entry[].changes[].value.text`: texto del comentario
- `entry[].changes[].value.from.id`: autor, cuando Meta lo entrega
- `entry[].changes[].value.from.username`: usuario, cuando Meta lo entrega
- `entry[].changes[].value.media.id`: `media_id`, cuando Meta lo entrega

## Permisos

Para el flujo actual con cuenta Instagram Business conectada a una Pagina de
Facebook, la hipotesis operativa es mantener los permisos ya usados por el
proyecto y validar si hay que anadir:

- `instagram_manage_comments`: leer/moderar/responder comentarios.

Permisos ya documentados para el proyecto:

- `instagram_basic`
- `pages_show_list`
- `pages_read_engagement`
- `instagram_manage_messages`
- `pages_messaging`

Antes de produccion, confirmar en documentacion oficial y en Meta App Review
que el permiso exacto es ese, que esta aprobado para la app y que el token de
larga duracion lo incluye.

## Endpoint de respuesta publica

El modulo esta preparado para usar este endpoint de Graph API, pendiente de
validacion real antes de activar produccion:

```text
POST https://graph.instagram.com/v25.0/{ig-comment-id}/replies
message=<respuesta_publica>
```

No se envian mensajes privados desde comentarios.

Tambien debe validarse si el endpoint exacto o los parametros cambian segun la
version de Graph API, el tipo de cuenta o los permisos concedidos.

## Politica funcional

Responde automaticamente, de forma corta y publica, a:

- felicitaciones;
- agradecimientos;
- preguntas generales de informacion;
- intencion de pedir informacion;
- intencion de reservar, derivando a WhatsApp.

No responde automaticamente a:

- quejas o reclamaciones;
- problemas medicos, reacciones, dolor, quemaduras o efectos adversos;
- preguntas sensibles;
- insultos;
- spam;
- comentarios sin suficiente significado;
- casos donde no sea seguro contestar publicamente.

Las respuestas publicas no confirman citas, disponibilidad, precios,
promociones ni informacion privada.

## Idempotencia y auditoria

Tabla PostgreSQL:

```sql
instagram_comment_events (
  comment_id TEXT PRIMARY KEY,
  media_id TEXT,
  author_id TEXT,
  author_username TEXT,
  comment_text TEXT NOT NULL,
  classification TEXT,
  status TEXT NOT NULL,
  response_text TEXT,
  error TEXT,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
```

Estados principales:

- `received`
- `dry_run`
- `published`
- `needs_review`
- `ignored`
- `ignored_own_account`
- `error`

Mapping operativo:

- `published` = respuesta publica enviada;
- `dry_run` = respuesta simulada, no publicada;
- `needs_review` = no responder automaticamente y revisar;
- `ignored` / `ignored_own_account` = omitido;
- `error` = fallo de procesamiento o publicacion;
- `received` = registrado inicialmente.

`comment_id` es clave primaria para evitar responder dos veces al mismo
comentario, incluso tras reinicios de Railway.

## Variables nuevas

```env
INSTAGRAM_COMMENTS_ENABLED=false
INSTAGRAM_COMMENTS_DRY_RUN=true
```

Comportamiento:

- `INSTAGRAM_COMMENTS_ENABLED` vacio o `false`: clasifica y registra, no publica.
- `INSTAGRAM_COMMENTS_DRY_RUN` ausente: se trata internamente como `true`.
- `INSTAGRAM_COMMENTS_ENABLED=true` y `INSTAGRAM_COMMENTS_DRY_RUN=true`: clasifica
  y registra, no publica.
- `INSTAGRAM_COMMENTS_ENABLED=true` y `INSTAGRAM_COMMENTS_DRY_RUN=false`: puede
  publicar respuestas reales para comentarios clasificados como seguros.

## Validacion antes de produccion

1. Desplegar con `INSTAGRAM_COMMENTS_ENABLED=false`.
2. Validar en documentacion oficial y en Meta Developer el permiso exacto,
   el field de webhook, la estructura de payload y el endpoint de respuesta.
3. Suscribir el campo de comentarios confirmado en Webhooks de la app de Meta.
4. Publicar o usar un comentario de prueba desde una cuenta tester.
5. Revisar logs de Railway: debe aparecer `dry-run` o no-publicacion.
6. Revisar PostgreSQL: `instagram_comment_events` debe registrar el comentario.
7. Confirmar que DMs siguen respondiendo igual.
8. Cambiar a `INSTAGRAM_COMMENTS_ENABLED=true` manteniendo
   `INSTAGRAM_COMMENTS_DRY_RUN=true`.
9. Solo tras revisar clasificaciones reales, poner
   `INSTAGRAM_COMMENTS_DRY_RUN=false`.

## Rollback

Rollback inmediato sin deploy:

```env
INSTAGRAM_COMMENTS_ENABLED=false
INSTAGRAM_COMMENTS_DRY_RUN=true
```

Rollback adicional en Meta:

- desuscribir el campo `comments`;
- mantener `messages` si se quiere conservar el agente de DMs.

No hace falta borrar la tabla de auditoria para detener las respuestas.
