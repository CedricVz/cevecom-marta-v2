# cevecom-marta-v2 — Contexto del proyecto

Sistema automatizado de contenido para Instagram para el centro de estética
**Marta Suñé Estilista & Estética Avanzada** (Barcelona). Arquitectura WAT: Workflows + Agents + Tools.

## Estado del proyecto (mayo 2026 — post-deploy Railway)

| Módulo | Estado | Pendiente |
|---|---|---|
| Módulo 1 v3 — Pipeline con guiones de Marta | 🟡 Listo — pendiente primer health check | Smoke test + lanzar Reels 1 y 2 manualmente |
| Módulo 2 — Agente de DMs | ✅ Activo en Railway (producción) | — |

**Datos del centro:**
- Nombre: Marta Suñé Estilista & Estética Avanzada
- Dirección: C/ Munné 15-17 bajos, Barcelona
- Ubicación: Barcelona
- Horario: martes a sábado de 10:00 a 19:30 (domingo y lunes cerrado)
- Web: martasune.es
- WhatsApp: 656 37 64 35

**Eliminados en limpieza mayo 2026** (pipeline v1/v2 y herramientas de setup):
- `tools/generar_guion.py`, `tools/leer_pendientes.py`, `tools/generar_calendario.py`
- `tools/setup_sheets.py`, `tools/setup_sheets_v3.py`
- `guiones.json`

**Correcciones aplicadas en auditoría mayo 2026:**
- `generar_video.py`: reemplazado MCP OAuth → token OAuth de `~/.claude/.credentials.json`
- `publicar_instagram.py`: eliminado `share_to_feed="true"` (deprecado en Meta API v25.0)
- `leer_calendario_drive.py`: lee de `CALENDARIO_MARTA_SHEETS_ID` (spreadsheet de Marta)
  y escribe al Pipeline `GOOGLE_SHEETS_ID`

**Deploy en Railway (mayo 2026):**
- `config.py`: acepta `GOOGLE_CREDENTIALS_JSON` (env var) o `GOOGLE_CREDENTIALS_PATH` (disco)
- `tools/db_context.py`: persistencia migrada de SQLite a PostgreSQL (Railway)
- `tools/dm_responder.py`: endpoint `/healthz` sin auth para healthcheck de Railway
- `railway.toml` + `Procfile`: deploy automático desde `main` → gunicorn 2 workers 4 threads
- Producción: `https://cevecom-marta-v2-production.up.railway.app`
- System prompt actualizado: identidad correcta (Marta Suñé Estilista & Estética Avanzada)
  + formato Instagram-friendly + horario y web del centro

---

## Módulos

### Módulo 1 v3 — Pipeline con guiones propios de Marta (ACTIVO)

Marta escribe directamente sus guiones en la pestaña **"Guiones_Marta"** del spreadsheet
`CALENDARIO_MARTA_SHEETS_ID`. El pipeline genera el vídeo y envía el email de aprobación.

```
pestaña "Guiones_Marta" en CALENDARIO_MARTA_SHEETS_ID (Marta escribe)
         ↓
leer_calendario_drive.py  → copia fila a Sheet1 (GOOGLE_SHEETS_ID) con Estado="Generando vídeo"
         ↓
generar_video.py           → HeyGen MCP (~6 créditos, 5-10 min)
         ↓
enviar_aprobacion.py       → email a Marta con preview + botones Aprobar/Rechazar
         ↓
publicar_instagram.py      → publica los Aprobados (ejecución independiente)
```

**Comando del pipeline:**
```
cmd /c "python tools\leer_calendario_drive.py | python tools\generar_video.py | python tools\enviar_aprobacion.py"
```

**Publicación tras aprobaciones:**
```
python tools/publicar_instagram.py
```

**Test individual con una_fila.json** (sin leer Sheets de Marta):
```
cmd /c "type una_fila.json | python tools\generar_video.py | python tools\enviar_aprobacion.py"
```
`una_fila.json` contiene el Reel de lanzamiento (presentación del clon de Marta, fila 2).

**Columnas que rellena Marta en "Guiones_Marta" (A–H):**

| Col | Campo | Ejemplo |
|-----|-------|---------|
| A | Tema | Radiofrecuencia facial — 3 beneficios |
| B | Tratamiento | Radiofrecuencia facial |
| C | Audiencia | Mujeres 30-50 con flacidez |
| D | Tono | Cercano, sin tecnicismos |
| E | Look_ID | (vacío = avatar predeterminado) |
| F | Fecha_deseada | 15/06/2026 |
| G | Guion | Texto completo que leerá el avatar |
| H | Notas_escenas | Dirección de escena para el Video Agent (planos, B-roll, transiciones) |

La columna I (`Estado_proceso`) la rellena el sistema. Marta NO la toca.

**Comportamiento de `leer_calendario_drive.py`:**
- Lee filas donde `Guion` ≠ vacío y `Estado_proceso` = vacío
- Copia cada fila al Pipeline (Sheet1 de `GOOGLE_SHEETS_ID`) con `Estado="Generando vídeo"`
- Marca `Estado_proceso = "Procesado ✓ YYYY-MM-DD HH:MM"` en la pestaña de Marta
- Idempotente: si se vuelve a ejecutar, no reprocesa filas ya marcadas

**Estados posibles en Sheet1 (pipeline):**
- `Pendiente` → fila lista para procesar
- `Generando vídeo` → vídeo HeyGen en proceso
- `Pendiente aprobación` → email enviado a Marta
- `Aprobado` / `Rechazado` → Marta decide desde el email
- `Publicado` → en Instagram
- `Error` → ver columna Errores + Reintentos

**Webhook de aprobación:** `appscript/aprobacion_webhook.gs` (desplegado en Apps Script)

---

### Módulo 2 — Agente de respuesta automática a DMs (ACTIVO — Producción en Railway)

Responde automáticamente a DMs de Instagram usando Meta Webhooks + OpenAI
Responses API + Flask. El contexto de cada conversación se persiste en
PostgreSQL (Railway) mediante `previous_response_id` de la Responses API.

**Arquitectura:**
```
DM cliente → Meta Webhooks → Railway: gunicorn + tools/dm_responder.py (Flask)
                                         │
                                         ├─ PostgreSQL Railway (tabla `dm_context`)
                                         ├─ OpenAI Responses API (gpt-4o + file_search)
                                         └─ Instagram Graph API (envía respuesta al DM)
```

**Producción (siempre activo, sin acción manual):**
- URL pública: `https://cevecom-marta-v2-production.up.railway.app`
- Webhook Meta apunta a `/webhook` con `META_WEBHOOK_VERIFY_TOKEN`
- Healthcheck en `/healthz` (200 OK)
- Deploy automático en cada push a `main`
- Logs y reinicios desde el dashboard de Railway

**Desarrollo local** (sólo si necesitas debug interactivo):
```powershell
# Terminal 1
python tools/dm_responder.py
# Terminal 2 — expón el endpoint local a internet
ngrok http 5000
# luego reconfigurar Meta webhook con la URL de ngrok (revertir después)
```

**Guía de configuración inicial de Meta:** `tools/configurar_meta_webhook.md`

**Migración SQLite → Postgres** (one-shot, ya realizada): `tools/migrar_sqlite_a_postgres.py`

---

## Variables de entorno

Ver `.env.example` para la referencia completa con instrucciones de obtención.

Todas las variables están configuradas. Las 5 variables Meta usan el System User
`CEVECOM Marta Reels` (ID: `61589023863845`):
- `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET`, `FACEBOOK_PAGE_ID`
- `INSTAGRAM_USER_ID`, `FACEBOOK_ACCESS_TOKEN`

Variables clave para el pipeline v3:
- `GOOGLE_SHEETS_ID` — spreadsheet del sistema (Sheet1 = pipeline)
- `CALENDARIO_MARTA_SHEETS_ID` — spreadsheet de Marta ("Calendario de Contenidos")
- `GOOGLE_CREDENTIALS_PATH` — ruta al JSON de la service account (modo local)

Variables exclusivas de Railway (producción):
- `GOOGLE_CREDENTIALS_JSON` — contenido completo del JSON de service account en
  una línea. `tools/google_creds.py` la prefiere sobre el archivo en disco.
- `DATABASE_URL` — connection string a PostgreSQL Railway. Si el Postgres está
  en el mismo proyecto, usar referencia `${{Postgres.DATABASE_URL}}` para que
  Railway la inyecte automáticamente.

---

## Pipeline de vídeo — configuración actual

**HeyGen — IDs y assets** (validados mayo 2026 — ver memoria `project_heygen_assets.md` para inventario completo del avatar group):
- **Look ID** (avatar usado en producción): `97175217da0f41edb57bd1aecd543792` — Photo Avatar (fuente landscape, portrait forzado por prompt)
- **Voice ID**: `dd40b7a452d34eb69c43f8ccc69800b2` — voz nativa del avatar
- **Brand Kit ID**: `bf6988fde35849079d09f9a6fa5b092d` — "Marta Suñé"
- **Avatar Group ID**: `5aacc60647784288ab1e92e0b269d639` (4 looks; 2 digital twins portrait sin uso disponibles si hay que migrar)
- **MCP**: `https://mcp.heygen.com/mcp/v1/` — añadido con `claude mcp add --transport http -s user heygen`
- **Token OAuth**: en `~/.claude/.credentials.json` · se renueva al abrir Claude Code
- **Coste**: ~6 créditos del plan web por vídeo (Video Agent)
- **REST API v2**: devuelve 403 — el plan de HeyGen no incluye acceso REST a generación
- **Pipeline MCP**: `create_video_agent` con `mode="generate"` + polling vía `get_video_agent_session`

**Identidad de marca inyectada al `agent_prompt`** (constantes en `tools/generar_video.py`):
- `BRAND_COLORS = "#D71F28 (rojo), #C5A059 (dorado), #605E5E (gris), #FFFFFF"`
- `CENTRO_DIR = "C/ Munné 15-17 bajos, Barcelona"`
- `BRAND_KIT_ID = "bf6988fde35849079d09f9a6fa5b092d"` — se pasa también al `create_video_agent`

**B-roll por tratamiento (`ASSET_URLS` en `tools/generar_video.py`):**

9 tratamientos con vídeo propio + `default` (vídeo de la entrada del salón).
Matching tolerante a acentos y mayúsculas vía `_asset_url_para_tratamiento(titulo)` (usa `unicodedata` para normalizar).

Claves mapeadas: `laser`, `depilacion`, `maderoterapia`, `drenaje`, `linfatico`, `criolipolisis`, `fotorejuvenecimiento`, `emslim` / `em slim`, `hifu`, `botox`. Cualquier `Tema` que no contenga uno de estos substrings cae al `default` (entrada del salón) — actualmente: radiofrecuencia, higiene facial, keratina, masaje, balayage, champú, celulitis.

**Notas_escenas (dirección de escena para el Video Agent):**
- Pestaña de Marta `Guiones_Marta`: **columna H**
- Pipeline `Sheet1`: **columna T (posición 20)** — header `Notas_escenas` (escrito vía gspread en esta sesión)
- Flujo: `leer_calendario_drive.py` la copia al Pipeline y la incluye en el JSON → `crear_video_heygen_mcp(texto, titulo, notas_escenas="")` la inyecta en el `agent_prompt` como bloque `SCENE DIRECTION (follow exactly): …` justo antes del script hablado.

**Nombre de marca oficial:** `Marta Suñé Estilista & Estética Avanzada` — unificado en mayo 2026 en `tools/dm_responder.py` (system prompt), `tools/generar_video.py` (agent_prompt) y este CLAUDE.md.

---

## Calendario actual (mayo 2026)

5 Reels pendientes en la pestaña `Guiones_Marta`. Todos con tema, tratamiento, audiencia, tono, guion y `notas_escenas` ya rellenos por Marta — listos para procesar.

| # | Contenido | Tratamiento |
|---|---|---|
| 1 | Vídeo de lanzamiento — presentación del clon de Marta | — |
| 2 | Celulitis | (cae a `default` en ASSET_URLS) |
| 3 | Champú | (cae a `default`) |
| 4 | HIFU | matchea `hifu` → B-roll propio |
| 5 | Balayage | (cae a `default` — peluquería sin B-roll dedicado) |

El vídeo 1 también vive en `una_fila.json` para test individual con:
```
cmd /c "type una_fila.json | python tools\generar_video.py | python tools\enviar_aprobacion.py"
```

---

## Entorno de desarrollo

- **SO**: Windows 10/11
- **Terminal**: cmd.exe — usar siempre `cmd /c` para pipes entre scripts
- **Evitar**: PowerShell para pipes (5.1 no pasa stdin correctamente)
- **Python**: ejecutar como `python` (no `python3`)
- **Rutas**: separador `\` en rutas locales
- **Editor**: VS Code con Claude Code

## Notas técnicas

- **Piping en Windows**: usar `cmd /c "a | b"` en lugar de PowerShell nativo
  (PowerShell 5.1 no pasa stdin correctamente entre procesos nativos).
- **UTF-8 en Windows**: `config.py` reconfigura explícitamente stdin/stdout/stderr
  a UTF-8 al arrancar para evitar errores de encoding en la consola.
- **generar_video.py — MCP auth**: lee el token OAuth de HeyGen de `~/.claude/.credentials.json`.
  Debe ejecutarse desde Claude Code. Si el token expira, lanza un error claro con instrucciones.
- **Dependencias**: todas en `requirements.txt`. Para dev local: `pip install -r requirements.txt`.
- **Deploy Railway**: definido en `railway.toml` (builder NIXPACKS, healthcheck
  `/healthz`, cron de publicación semanal `0 10 * * 1`) + `Procfile`
  (gunicorn 2 workers 4 threads). Trigger: push a `main` → redeploy automático.
- **Meta Graph API — versión**: `publicar_instagram.py` y `dm_responder.py` usan
  `graph.instagram.com/v25.0` en todos los endpoints.
- **System User Meta**: `CEVECOM Marta Reels` (ID: `61589023863845`) — tiene acceso
  a la Página de Facebook, la App y la cuenta de Instagram de Marta. El
  `FACEBOOK_ACCESS_TOKEN` del `.env` pertenece a este System User.

---

## Flujo de trabajo mensual completo

```
[Marta rellena la pestaña "Guiones_Marta" en su spreadsheet]
  → Columnas A-H: Tema, Tratamiento, Audiencia, Tono, Look_ID, Fecha_deseada, Guion, Notas_escenas
  → Deja columna I (Estado_proceso) en blanco

[Pipeline — cuando Marta ha rellenado sus filas]
cmd /c "python tools\leer_calendario_drive.py | python tools\generar_video.py | python tools\enviar_aprobacion.py"
  → Copia filas al Pipeline, genera vídeo HeyGen (~6 créditos, 5-10 min), envía email a Marta

[Marta aprueba en el email]
  → Webhook de Apps Script → Estado cambia a "Aprobado" en Sheet1

[Publicación]
python tools/publicar_instagram.py
  → También se ejecuta automáticamente desde el cron de Railway los lunes a las 10:00 UTC

[Servidor de DMs — Railway en producción (siempre activo, sin acción manual)]
URL pública: https://cevecom-marta-v2-production.up.railway.app
Redeploy automático en cada push a main.
Debug local: python tools/dm_responder.py + ngrok http 5000
```

---

## Próximo paso

**Módulo 1 — primer health check del pipeline** (siguiente sesión):

1. **Smoke test** con el Reel de lanzamiento (sin tocar el calendario de Marta):
   ```
   cmd /c "type una_fila.json | python tools\generar_video.py | python tools\enviar_aprobacion.py"
   ```
   Verificar en HeyGen Video Agent: orientación 9:16, B-roll del Drive intercalado, brand kit aplicado, scene direction respetada.

2. **Lanzamiento manual** de los Reels 1 y 2 del calendario con aprobación de Marta vía email. QA visual end-to-end antes de seguir.

3. **Activación del automatismo** una vez validados los dos primeros: el cron de Railway publica los `Aprobados` los lunes a las 10:00 UTC. El pipeline (`leer_calendario_drive → generar_video → enviar_aprobacion`) se sigue ejecutando manualmente; cron solo se encarga de `publicar_instagram.py`.

Módulo 2 sigue vivo respondiendo DMs en producción sin intervención.
