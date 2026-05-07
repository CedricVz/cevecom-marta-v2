# Guía: Configurar Meta Webhook para DMs de Instagram

Sigue estos pasos para conectar Instagram con el servidor `dm_responder.py`.
Necesitarás acceso al panel de desarrolladores de Facebook y una cuenta de
Facebook App con Instagram configurado como producto.

---

## Requisitos previos

- Python instalado con las dependencias del proyecto (`pip install -r requirements.txt`)
- ngrok instalado ([ngrok.com/download](https://ngrok.com/download))
- Una Facebook App creada en [developers.facebook.com](https://developers.facebook.com)
- La cuenta de Instagram de Marta configurada como cuenta Business/Creator
- La cuenta de Instagram conectada a una Página de Facebook

---

## Paso 1 — Obtener los IDs de Facebook / Instagram

Antes de configurar el webhook necesitas estos valores para el `.env`:

### FACEBOOK_APP_ID y FACEBOOK_APP_SECRET
1. Ve a [developers.facebook.com/apps](https://developers.facebook.com/apps)
2. Selecciona tu app → **Configuración → Básica**
3. Copia "ID de la aplicación" y "Clave secreta de la app"

### FACEBOOK_ACCESS_TOKEN (token de corta duración → convertir a 60 días)
1. Ve a [developers.facebook.com/tools/explorer](https://developers.facebook.com/tools/explorer)
2. Selecciona tu App en el desplegable superior
3. Haz clic en "Generar token de acceso"
4. Marca estos permisos:
   - `instagram_manage_messages`
   - `instagram_basic`
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
   - `pages_messaging`
5. Copia el token (válido ~1 hora)
6. Conviértelo a token de 60 días con Graph API Explorer:
   ```
   GET /oauth/access_token
     grant_type=fb_exchange_token
     client_id={FACEBOOK_APP_ID}
     client_secret={FACEBOOK_APP_SECRET}
     fb_exchange_token={TOKEN_CORTA_DURACION}
   ```
7. Copia el nuevo token y ponlo en `.env` como `FACEBOOK_ACCESS_TOKEN`

### FACEBOOK_PAGE_ID
```
GET /me/accounts
```
(con el token de acceso) → busca la Página de Facebook de Marta → copia el `id`

### INSTAGRAM_USER_ID
```
GET /{FACEBOOK_PAGE_ID}?fields=instagram_business_account
```
→ el resultado tiene `{ "instagram_business_account": { "id": "XXXX" } }` → copia el `id`

---

## Paso 2 — Rellenar el .env

```env
FACEBOOK_APP_ID=<tu_app_id>
FACEBOOK_APP_SECRET=<tu_app_secret>
FACEBOOK_PAGE_ID=<id_pagina_facebook>
INSTAGRAM_USER_ID=<id_cuenta_instagram>
FACEBOOK_ACCESS_TOKEN=<token_60_dias>
META_WEBHOOK_VERIFY_TOKEN=cevecom_webhook_secret_2026
```

---

## Paso 3 — Arrancar el servidor local

```powershell
cd "c:\Users\SONY\cevecom-marta-v2"
python tools/dm_responder.py
```

Verás en la consola:
```
[dm_responder] dm_responder arrancando en http://localhost:5000
[dm_responder] Expón el endpoint con: ngrok http 5000 → configura la URL en Facebook App → Webhooks
```

---

## Paso 4 — Exponer con ngrok

En otra terminal:

```powershell
ngrok http 5000
```

Copia la URL pública que aparece, por ejemplo:
```
https://xxxx.ngrok-free.app
```

La URL cambia cada vez que reinicias ngrok (en el plan gratuito). Para una URL fija,
considera el plan de pago de ngrok o usar un VPS.

---

## Paso 5 — Configurar el webhook en Facebook App

1. Ve a [developers.facebook.com/apps](https://developers.facebook.com/apps) → tu App
2. En el menú lateral: **Productos → Webhooks**
3. Haz clic en **"Añadir suscripción"** (o **"Editar"** si ya existe)
4. Selecciona **"Instagram"** en el desplegable de objeto
5. Rellena:
   - **URL de devolución de llamada**: `https://xxxx.ngrok-free.app/webhook`
   - **Token de verificación**: `cevecom_webhook_secret_2026` (igual que `META_WEBHOOK_VERIFY_TOKEN` en `.env`)
6. Haz clic en **"Verificar y guardar"**
   - Meta llamará a tu URL con un GET de verificación
   - El servidor debe responder con el `hub.challenge` — verás en los logs: `Webhook verificado por Meta.`

---

## Paso 6 — Suscribir al campo `messages`

Después de verificar el webhook:

1. En la misma página de Webhooks → sección Instagram
2. Haz clic en **"Suscribirse"** junto al campo **`messages`**
3. También suscríbete a `messaging_postbacks` si quieres gestionar botones en el futuro

---

## Paso 7 — Verificar permisos de la App

En **Revisión de la app → Permisos y funciones**, asegúrate de que estos permisos estén
aprobados (algunos requieren revisión de Meta para uso en producción):

| Permiso | Necesario para |
|---|---|
| `instagram_manage_messages` | Recibir y enviar DMs |
| `pages_messaging` | Enviar mensajes vía API |
| `instagram_basic` | Leer info básica de la cuenta |

Durante el desarrollo puedes usar el **modo de prueba** sin revisión, pero solo para
usuarios añadidos como tester/developer en la app.

---

## Paso 8 — Test en producción

1. Desde una cuenta de Instagram diferente a la de Marta, envía un DM a la cuenta del centro
2. En los logs del servidor verás:
   ```
   [dm_responder] DM recibido de 123456789: Hola, qué tratamientos tenéis?
   [dm_responder] DM respondido → sender=123456789 | prev=None → nuevo=resp_abc123
   ```
3. El cliente recibirá la respuesta automática en segundos

---

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| Webhook no verifica | Token incorrecto | Comprueba que `META_WEBHOOK_VERIFY_TOKEN` en `.env` coincide con el token en Facebook App |
| Error 401 en eventos POST | Firma HMAC inválida | Comprueba `FACEBOOK_APP_SECRET` en `.env` |
| No llegan eventos | Webhook no suscrito a `messages` | Revisa las suscripciones en Webhooks → Instagram |
| OpenAI error | Clave inválida o créditos insuficientes | Comprueba `OPENAI_API_KEY` y créditos en platform.openai.com |
| Meta error al enviar DM | Token expirado | Renueva `FACEBOOK_ACCESS_TOKEN` |
| ngrok URL cambia | Plan gratuito de ngrok | Reconfigura el webhook cada vez, o usa ngrok de pago |
