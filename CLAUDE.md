# cevecom-marta-v2 — Contexto del proyecto

Sistema automatizado de contenido para Instagram para el centro de estética
**Marta Suñé Estilista y Estética** (Barcelona). Arquitectura WAT: Workflows + Agents + Tools.

## Estado del proyecto (mayo 2026 — post-limpieza v3)

| Módulo | Estado | Pendiente |
|---|---|---|
| Módulo 1 v3 — Pipeline con guiones de Marta | ✅ Activo y validado | — |
| Módulo 2 — Agente de DMs | ✅ Construido | Configurar Facebook App + webhook en developers.facebook.com |

**Eliminados en limpieza mayo 2026** (pipeline v1/v2 y herramientas de setup):
- `tools/generar_guion.py`, `tools/leer_pendientes.py`, `tools/generar_calendario.py`
- `tools/setup_sheets.py`, `tools/setup_sheets_v3.py`
- `guiones.json`

**Correcciones aplicadas en auditoría mayo 2026:**
- `generar_video.py`: reemplazado MCP OAuth → token OAuth de `~/.claude/.credentials.json`
- `publicar_instagram.py`: eliminado `share_to_feed="true"` (deprecado en Meta API v25.0)
- `leer_calendario_drive.py`: lee de `CALENDARIO_MARTA_SHEETS_ID` (spreadsheet de Marta)
  y escribe al Pipeline `GOOGLE_SHEETS_ID`

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

**Columnas que rellena Marta en "Guiones_Marta" (A–G):**

| Col | Campo | Ejemplo |
|-----|-------|---------|
| A | Tema | Radiofrecuencia facial — 3 beneficios |
| B | Tratamiento | Radiofrecuencia facial |
| C | Audiencia | Mujeres 30-50 con flacidez |
| D | Tono | Cercano, sin tecnicismos |
| E | Look_ID | (vacío = avatar predeterminado) |
| F | Fecha_deseada | 15/06/2026 |
| G | Guion | Texto completo que leerá el avatar |

La columna H (`Estado_proceso`) la rellena el sistema. Marta NO la toca.

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

### Módulo 2 — Agente de respuesta automática a DMs (CONSTRUIDO)

Responde automáticamente a DMs de Instagram usando Meta Webhooks + OpenAI
Responses API + Flask + ngrok. El contexto de cada conversación se persiste
en SQLite mediante `previous_response_id`.

**Arquitectura:**
```
DM de cliente → Meta Webhooks → tools/dm_responder.py (Flask)
                                         │
                                         ├─ SQLite dm_context.db (contexto por usuario)
                                         ├─ OpenAI Responses API (gpt-4o + file_search)
                                         └─ Instagram Graph API (envía respuesta al DM)
```

**Arranque:**
```powershell
# Terminal 1
python tools/dm_responder.py
# Terminal 2
ngrok http 5000
```

**Guía de configuración:** `tools/configurar_meta_webhook.md`

**Pendiente para activar el Módulo 2:**
- Configurar la Facebook App en [developers.facebook.com](https://developers.facebook.com)
  - La app está creada en el **portfolio empresarial de Marta**
  - Añadir producto **Instagram** a la app
  - Configurar webhook con la URL de ngrok y `META_WEBHOOK_VERIFY_TOKEN`
  - Suscribir al campo `messages`

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
- `GOOGLE_CREDENTIALS_PATH` — ruta al JSON de la service account

---

## HeyGen

- **Look ID**: `97175217da0f41edb57bd1aecd543792` (photo avatar — único avatar configurado)
- **Voice ID**: `dd40b7a452d34eb69c43f8ccc69800b2` — voz nativa validada del avatar (mayo 2026)
- **Avatar ID UI / Group ID**: `5aacc60647784288ab1e92e0b269d639` (referencia visual, no se usa en código)
- **MCP**: `https://mcp.heygen.com/mcp/v1/` — añadido con `claude mcp add --transport http -s user heygen`
- **Token OAuth**: almacenado en `~/.claude/.credentials.json` · se renueva al abrir Claude Code
- **Coste**: ~6 créditos del plan web por vídeo (Video Agent)
- **REST API v2**: devuelve 403 — el plan de HeyGen no incluye acceso REST a generación de vídeo
- **Pipeline MCP**: validado mayo 2026 — creación via `create_video_agent` + polling via `get_video_agent_session`

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
- **Módulo 2 — dependencias**: `pip install flask openai` si no están instaladas.
- **Meta Graph API — versión**: `publicar_instagram.py` y `dm_responder.py` usan
  `graph.instagram.com/v25.0` en todos los endpoints.
- **System User Meta**: `CEVECOM Marta Reels` (ID: `61589023863845`) — tiene acceso
  a la Página de Facebook, la App y la cuenta de Instagram de Marta. El
  `FACEBOOK_ACCESS_TOKEN` del `.env` pertenece a este System User.

---

## Flujo de trabajo mensual completo

```
[Marta rellena la pestaña "Guiones_Marta" en su spreadsheet]
  → Columnas A-G: Tema, Tratamiento, Audiencia, Tono, Look_ID, Fecha_deseada, Guion
  → Deja columna H (Estado_proceso) en blanco

[Pipeline — cuando Marta ha rellenado sus filas]
cmd /c "python tools\leer_calendario_drive.py | python tools\generar_video.py | python tools\enviar_aprobacion.py"
  → Copia filas al Pipeline, genera vídeo HeyGen (~6 créditos, 5-10 min), envía email a Marta

[Marta aprueba en el email]
  → Webhook de Apps Script → Estado cambia a "Aprobado" en Sheet1

[Publicación]
python tools/publicar_instagram.py

[Servidor de DMs — continuo]
python tools/dm_responder.py   # + ngrok http 5000 en otra terminal
```

---

## Próximo paso

Test de lanzamiento con el Reel de presentación del clon:

```
cmd /c "type una_fila.json | python tools\generar_video.py | python tools\enviar_aprobacion.py"
```

`una_fila.json` contiene el guion de presentación de Marta a sus seguidores
(Estado="Pendiente" en Sheet1 fila 2, listo para procesar).
