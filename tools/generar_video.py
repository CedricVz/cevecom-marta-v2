"""
tools/generar_video.py — Genera vídeos en HeyGen para cada guión.

Lee guiones JSON desde stdin (salida de generar_guion.py),
envía cada guión a HeyGen, espera a que se renderice, actualiza
Google Sheets con el resultado y pasa el JSON enriquecido a stdout.

IMPORTANTE: este script debe ejecutarse desde una sesión de Claude Code
(no desde terminal standalone) porque lee el token OAuth de HeyGen de
~/.claude/.credentials.json. Si el token expira, Claude Code lo renueva
automáticamente al abrir una sesión.

Uso:
    python tools/generar_guion.py | python tools/generar_video.py
    echo '[{"fila":2,"guion":"...", ...}]' | python tools/generar_video.py
"""

import json
import logging
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import gspread
import requests
from gspread.utils import rowcol_to_a1

from config import cfg
from tools._columnas import COL
from tools.google_creds import service_account_credentials

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger("generar_video")

SCOPES_WRITE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# ── HeyGen ───────────────────────────────────────────────────────────────────
HEYGEN_MCP_URL = "https://mcp.heygen.com/mcp/v1/"

HEYGEN_LOOK_ID = "97175217da0f41edb57bd1aecd543792"
VOICE_ID       = "dd40b7a452d34eb69c43f8ccc69800b2"  # voz nativa del avatar
BRAND_COLORS   = "#D71F28 (rojo), #C5A059 (dorado), #605E5E (gris), #FFFFFF"
CENTRO_DIR     = "C/ Munné 15-17 bajos, Barcelona"
BRAND_KIT_ID   = "bf6988fde35849079d09f9a6fa5b092d"

ASSET_URLS = {
    "laser":               "https://drive.google.com/file/d/1tulapnMn_VkVkQkzlRbS_Aqj357__iZa/view",
    "depilacion":          "https://drive.google.com/file/d/1tulapnMn_VkVkQkzlRbS_Aqj357__iZa/view",
    "maderoterapia":       "https://drive.google.com/file/d/1s3SoIaGPp_wPT2LuIAj0xV2nNlkQtEJI/view",
    "drenaje":             "https://drive.google.com/file/d/1kZKbnmk2SKjwDkNSIdOdZthT72zw3QET/view",
    "linfatico":           "https://drive.google.com/file/d/1kZKbnmk2SKjwDkNSIdOdZthT72zw3QET/view",
    "criolipolisis":       "https://drive.google.com/file/d/1baExmH8XdAfKvwx6J7h9NmD3Ay74w1-M/view",
    "fotorejuvenecimiento":"https://drive.google.com/file/d/1PtYQinK45J6VpQWz3Wl3t2WUO-2By01N/view",
    "emslim":              "https://drive.google.com/file/d/1WPGzNzlQxMJ5GShgcI97W4ae4JMpQQPG/view",
    "em slim":             "https://drive.google.com/file/d/1WPGzNzlQxMJ5GShgcI97W4ae4JMpQQPG/view",
    "hifu":                "https://drive.google.com/file/d/1nVHmDk2XFoRF3IRINfcp1_quJFMn07Ch/view",
    "botox":               "https://drive.google.com/file/d/1MUdQgyy23Vgy614Qa8jwgxwBlnfadEz5/view",
    "default":             "https://drive.google.com/file/d/1vfjVics-_7SlWhvymHVnq1oRrcP5hroM/view"
}

POLL_INTERVALO = 15    # segundos entre checks de estado
POLL_TIMEOUT   = 900   # 15 minutos máximo por vídeo


def conectar_sheets() -> gspread.Worksheet:
    creds = service_account_credentials(SCOPES_WRITE)
    gc = gspread.authorize(creds)
    return gc.open_by_key(cfg.google_sheets_id).sheet1


def actualizar_fila(hoja: gspread.Worksheet, fila: int, updates: dict[str, str]) -> None:
    payload = [
        {"range": rowcol_to_a1(fila, col), "values": [[valor]]}
        for nombre, valor in updates.items()
        if (col := COL.get(nombre)) is not None
    ]
    if payload:
        hoja.batch_update(payload)


def leer_reintentos(hoja: gspread.Worksheet, fila: int) -> int:
    try:
        valor = hoja.cell(fila, COL["Reintentos"]).value
        return int(valor) if valor else 0
    except Exception:
        return 0


def extraer_texto_hablado(guion: str) -> str:
    """Elimina las etiquetas estructurales [GANCHO - 5s] etc. del guión."""
    texto = re.sub(r"\[.+?\]\n?", "", guion)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _leer_token_oauth_heygen() -> str:
    """Lee el token OAuth de HeyGen desde las credenciales de Claude Code."""
    creds_path = Path.home() / ".claude" / ".credentials.json"
    if not creds_path.exists():
        raise RuntimeError(
            "No se encontró ~/.claude/.credentials.json — abre Claude Code y "
            "ejecuta: claude mcp add --transport http -s user heygen https://mcp.heygen.com/mcp/v1/"
        )
    with open(creds_path, encoding="utf-8") as f:
        creds = json.load(f)
    for key, entry in creds.get("mcpOAuth", {}).items():
        if key.startswith("heygen|") or entry.get("serverName") == "heygen":
            expires_at = float(entry.get("expiresAt") or 0) / 1000
            if time.time() > expires_at:
                raise RuntimeError(
                    "Token OAuth de HeyGen expirado. Abre Claude Code para renovarlo automáticamente."
                )
            return entry["accessToken"]
    raise RuntimeError("No se encontró token OAuth de HeyGen en .credentials.json")


def _asset_url_para_tratamiento(titulo: str) -> str:
    def quitar_acentos(s):
        return ''.join(
            c for c in unicodedata.normalize('NFD', s)
            if unicodedata.category(c) != 'Mn'
        )
    t = quitar_acentos(titulo.lower())
    for key in ASSET_URLS:
        if quitar_acentos(key) in t:
            return ASSET_URLS[key]
    return ASSET_URLS["default"]


def _llamar_mcp_heygen(tool_name: str, arguments: dict, token: str, timeout: int = 60) -> dict:
    """Invoca una tool del MCP de HeyGen via JSON-RPC sobre HTTP.

    El servidor responde con SSE (`event: message\\ndata: <jsonrpc_envelope>`).
    Devuelve el dict resultado de parsear `result.content[0].text` (string JSON).
    Lanza RuntimeError si la tool reporta isError o si hay JSON-RPC `error`.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": tool_name,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    r = requests.post(HEYGEN_MCP_URL, headers=headers, json=payload, timeout=timeout)
    r.raise_for_status()
    data_line = next(
        (line[len("data: "):] for line in r.text.splitlines() if line.startswith("data: ")),
        None,
    )
    if not data_line:
        raise RuntimeError(f"Respuesta MCP sin línea `data:`: {r.text!r}")
    envelope = json.loads(data_line)
    if "error" in envelope:
        raise RuntimeError(f"MCP {tool_name} JSON-RPC error: {envelope['error']}")
    result = envelope.get("result", {})
    if result.get("isError"):
        raise RuntimeError(f"MCP {tool_name} isError=True: {result}")
    content = result.get("content") or []
    if not content or "text" not in content[0]:
        raise RuntimeError(f"MCP {tool_name} sin content[0].text: {result}")
    try:
        return json.loads(content[0]["text"])
    except json.JSONDecodeError:
        return {"text": content[0]["text"]}


def crear_video_heygen_mcp(texto: str, titulo: str, notas_escenas: str = "") -> str:
    """Crea el vídeo via Video Agent MCP (~6 créditos, plan web) y devuelve session_id.

    El video_id no está disponible al crear — se obtiene al final del polling
    en `esperar_video_heygen_mcp` (que también devuelve la URL).
    """
    token = _leer_token_oauth_heygen()
    asset_url = _asset_url_para_tratamiento(titulo)
    scene_direction = (
        f"SCENE DIRECTION (follow exactly):\n{notas_escenas}\n\n"
        if notas_escenas else ""
    )
    agent_prompt = (
        f"Create a 9:16 VERTICAL portrait Instagram Reel "
        f"(720x1280px, 35-45 seconds) for 'Marta Suñé Estilista "
        f"& Estética Avanzada', a premium beauty center in Barcelona "
        f"at {CENTRO_DIR}. "
        f"CRITICAL OUTPUT REQUIREMENT: The final video MUST be vertical "
        f"9:16 portrait format. "
        f"AVATAR FRAMING: Place avatar {HEYGEN_LOOK_ID} as a portrait "
        f"talking head — crop and frame to show face and upper body "
        f"centered in a vertical 9:16 composition. The avatar source "
        f"is landscape but the OUTPUT must be portrait. "
        f"Use voice ID {VOICE_ID}. "
        f"Brand colors: {BRAND_COLORS}. Apply to text overlays and "
        f"graphic elements. Brand kit ID: {BRAND_KIT_ID}. "
        f"VIDEO STRUCTURE: "
        f"[0-3s] Avatar talking head, beauty clinic background, "
        f"warm professional lighting, portrait framing. "
        f"[3-35s] Avatar speaks script, intercut with real footage "
        f"from the center: {asset_url} — use this as B-roll. "
        f"Show hands-on treatment, professional equipment, "
        f"actual clinic space. NO generic stock footage. "
        f"All B-roll must be portrait 9:16. "
        f"[35-45s] Avatar delivers CTA, 'Marta Suñé' branding visible. "
        f"STYLE: warm, professional, approachable. "
        f"{scene_direction}"
        f"Speak EXACTLY this script word for word:\n\n{texto}"
    )
    result = _llamar_mcp_heygen("create_video_agent", {
        "mode": "generate",
        "orientation": "portrait",
        "avatarId": HEYGEN_LOOK_ID,
        "voiceId": VOICE_ID,
        "brandKitId": BRAND_KIT_ID,
        "prompt": agent_prompt,
    }, token, timeout=120)
    session_id = result.get("session_id")
    if not session_id:
        raise RuntimeError(f"create_video_agent sin session_id: {result}")
    return session_id


def esperar_video_heygen_mcp(session_id: str) -> tuple[str, str]:
    """Polling de la Video Agent session hasta status=completed.

    Devuelve `(video_url, video_id)`. La URL viene del MCP tool `get_video`
    (paso separado tras detectar completed), no de `get_video_agent_session`.
    """
    token = _leer_token_oauth_heygen()
    transcurrido = 0

    while transcurrido < POLL_TIMEOUT:
        session = _llamar_mcp_heygen("get_video_agent_session",
                                     {"session_id": session_id},
                                     token, timeout=30)
        estado = session.get("status", "")
        video_id = session.get("video_id", "")
        progress = session.get("progress")
        logger.info("session_id=%s status=%s progress=%s video_id=%s (%ds)",
                    session_id, estado, progress, video_id, transcurrido)

        if estado == "completed":
            if not video_id:
                raise RuntimeError(f"Session completada pero sin video_id: {session}")
            video = _llamar_mcp_heygen("get_video", {"video_id": video_id},
                                       token, timeout=30)
            video_url = video.get("video_url")
            if not video_url:
                raise RuntimeError(f"get_video sin video_url: {video}")
            return video_url, video_id
        if estado in ("failed", "error"):
            raise RuntimeError(f"HeyGen falló: status={estado}. session={session}")

        time.sleep(POLL_INTERVALO)
        transcurrido += POLL_INTERVALO

    raise TimeoutError(f"Session {session_id} no completada tras {POLL_TIMEOUT}s")


def _registrar_error(hoja: gspread.Worksheet, fila: int, mensaje: str) -> None:
    reintentos = leer_reintentos(hoja, fila) + 1
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    actualizar_fila(hoja, fila, {
        "Estado": "Error",
        "Errores": f"{timestamp} | {mensaje}",
        "Reintentos": str(reintentos),
    })


def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        logger.error("No se recibió JSON por stdin.")
        sys.exit(1)

    try:
        guiones: list[dict] = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("JSON inválido en stdin: %s", e)
        sys.exit(1)

    if not guiones:
        logger.info("0 guiones recibidos. Nada que procesar.")
        print("[]")
        return

    try:
        hoja = conectar_sheets()
    except Exception as e:
        logger.error("Error conectando a Google Sheets: %s", e)
        sys.exit(1)

    resultados = []

    for item in guiones:
        fila = item["fila"]
        logger.info("Fila %d → generando vídeo: %s", fila, item["tema"])

        try:
            texto = extraer_texto_hablado(item["guion"])

            session_id = crear_video_heygen_mcp(
                texto, item["tema"], notas_escenas=item.get("notas_escenas", "")
            )
            # Guarda session_id inmediatamente: si el proceso falla durante el
            # polling se puede retomar el job que ya consumió créditos.
            actualizar_fila(hoja, fila, {"ID_heygen": session_id})
            logger.info("Fila %d: job enviado — session_id=%s", fila, session_id)

            video_url, video_id = esperar_video_heygen_mcp(session_id)

            actualizar_fila(hoja, fila, {
                "ID_heygen": video_id,
                "Video_preview": video_url,
                "Estado": "Pendiente aprobación",
                "Errores": "",
            })

            resultados.append({**item, "video_url": video_url})
            logger.info("Fila %d: OK → %s", fila, video_url)

        except RuntimeError as e:
            logger.error("Fila %d: error HeyGen — %s", fila, e)
            _registrar_error(hoja, fila, str(e))

        except TimeoutError as e:
            logger.error("Fila %d: timeout — %s", fila, e)
            _registrar_error(hoja, fila, str(e))

        except Exception as e:
            logger.error("Fila %d: error inesperado — %s: %s", fila, type(e).__name__, e)
            _registrar_error(hoja, fila, f"{type(e).__name__}: {e}")

    logger.info(
        "%d/%d vídeos generados con éxito.",
        len(resultados),
        len(guiones),
    )
    print(json.dumps(resultados, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
