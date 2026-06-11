# Workflow: Agente de respuesta automática a DMs de Instagram

## Objetivo
Responder automáticamente a los DMs de Instagram de los clientes del centro de estética
usando la OpenAI Responses API con vector store de conocimiento. El contexto de
conversación por usuario se persiste en SQLite mediante `previous_response_id`.

## Módulo
Módulo 2 — independiente del Módulo 1 (Reels).

## Arquitectura

```
Cliente envía DM a Instagram
        │
        ▼
Meta Webhooks → POST /webhook (ngrok → localhost:5000)
        │
        ├─ Verificación HMAC-SHA256 (X-Hub-Signature-256)
        │
        ├─ Responde 200 OK inmediatamente (< 5s requerido por Meta)
        │
        └─ Thread de fondo:
               │
               ├─ Detectar intención de cita/reserva/cambio/cancelación
               │   └─ Si coincide: responder WhatsApp 656 376 435
               │      sin OpenAI, sin memoria y sin simular agenda
               │
               ├─ Si no es reserva: leer previous_response_id de SQLite (dm_context.db)
               │
               ├─ OpenAI Responses API
               │   model: gpt-4o
               │   tools: file_search → OPENAI_VECTOR_STORE_ID
               │   previous_response_id: (encadena contexto de conversación)
               │
               ├─ Guardar nuevo response_id en SQLite
               │
               ├─ Meta Graph API → enviar respuesta al DM
               │
               └─ Si error: email a EMAIL_COPIA_PRESTADOR
```

## Recursos ya creados
- **Vector Store ID**: `vs_69ea49679ce481918f6290836692c47f`
  - Contiene: precios, tratamientos, FAQ, horarios, política de cancelación
- **Assistant ID**: `asst_tL5WYNDN1dEk2qb08pTlqyqx`
  - (Referencia histórica — la implementación actual usa Responses API, no Assistants API)

## Herramienta principal
`tools/dm_responder.py` — servidor Flask con todos los componentes integrados

## Deployment local con ngrok

```powershell
# Terminal 1 — arrancar el servidor
python tools/dm_responder.py

# Terminal 2 — exponer públicamente
ngrok http 5000
# Copiar la URL pública (ej: https://xxxx.ngrok-free.app)
# Configurar en: Facebook App → Webhooks → URL del callback
```

## Variables de entorno necesarias

| Variable | Descripción |
|---|---|
| `OPENAI_API_KEY` | Clave de OpenAI |
| `OPENAI_VECTOR_STORE_ID` | ID del vector store (ya configurado) |
| `META_WEBHOOK_VERIFY_TOKEN` | Token secreto para verificar el webhook |
| `FACEBOOK_APP_SECRET` | Para verificar firma HMAC de eventos |
| `FACEBOOK_ACCESS_TOKEN` | Token de acceso Meta (60 días) |
| `INSTAGRAM_USER_ID` | ID de la cuenta de Instagram de Marta |
| `EMAIL_SMTP_*` | Configuración SMTP (para notificaciones de error) |
| `EMAIL_COPIA_PRESTADOR` | Email que recibe alertas de error técnico |

## Persistencia de contexto

SQLite `dm_context.db` (raíz del proyecto):
- Tabla `contexto`: `instagram_user_id` → `response_id`
- Cada respuesta de OpenAI devuelve un `response_id` que se pasa como
  `previous_response_id` en el siguiente turno del mismo usuario
- Esto permite a OpenAI recuperar el contexto de la conversación sin
  mantener el historial de mensajes en local

## Casos especiales

| Caso | Comportamiento |
|---|---|
| Primera vez que escribe un usuario | No hay `previous_response_id` → nueva conversación |
| Pregunta fuera de conocimiento | El agente redirige a WhatsApp 656 376 435 |
| Petición de cita, reserva, hueco, disponibilidad, cambio o cancelación | Respuesta fija a WhatsApp 656 376 435, sin llamar OpenAI ni simular agenda |
| Error de OpenAI o Meta | Log + email a `EMAIL_COPIA_PRESTADOR` |
| Mensaje del propio Instagram (eco) | Ignorado (`sender_id == instagram_user_id`) |
| Mensaje sin texto (sticker, imagen) | Ignorado |

## Test de verificación

```powershell
# 1. Comprobar que el endpoint GET responde al verify token
curl "http://localhost:5000/webhook?hub.mode=subscribe&hub.verify_token=cevecom_webhook_secret_2026&hub.challenge=TEST123"
# Respuesta esperada: TEST123

# 2. Simular evento POST (sin firma HMAC — válido en local)
curl -X POST http://localhost:5000/webhook `
  -H "Content-Type: application/json" `
  -d '{\"entry\":[{\"messaging\":[{\"sender\":{\"id\":\"123\"},\"message\":{\"text\":\"Hola, qué tratamientos tenéis?\"}}]}]}'
# Respuesta esperada: {\"status\": \"ok\"}
# El DM de respuesta llegará a Instagram en unos segundos
```

## Estado actual

- [x] `tools/dm_responder.py` — lógica completa implementada
- [x] SQLite `dm_context.db` — persistencia de contexto por usuario
- [x] OpenAI Responses API con `previous_response_id`
- [x] Meta Webhooks endpoint GET + POST
- [x] Verificación HMAC-SHA256
- [x] Notificaciones de error por email
- [ ] Credenciales Meta reales en `.env` (`FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, etc.)
- [ ] Configuración del webhook en Facebook App (ver `tools/configurar_meta_webhook.md`)
- [ ] Test en producción con DM real desde Instagram
