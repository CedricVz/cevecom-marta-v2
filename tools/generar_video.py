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
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import anthropic as anthropic_sdk
import gspread
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


def crear_video_heygen_mcp(texto: str, titulo: str) -> tuple[str, str]:
    """Crea el vídeo via Video Agent MCP (~6 créditos, créditos plan web) y devuelve (video_id, session_id)."""
    token = _leer_token_oauth_heygen()
    client = anthropic_sdk.Anthropic(api_key=cfg.anthropic_api_key)
    agent_prompt = (
        f"Create a professional vertical Instagram Reel (9:16, 35-40 seconds) "
        f"for a beauty and aesthetics center in Barcelona called Cevecom Marta. "
        f"Use avatar ID {HEYGEN_LOOK_ID} and voice ID {VOICE_ID}. "
        f"The avatar must speak exactly this script:\n\n{texto}"
    )
    prompt = (
        f'Use the HeyGen tool create_video_agent with these exact parameters: '
        f'mode="generate", orientation="portrait", '
        f'avatarId="{HEYGEN_LOOK_ID}", voiceId="{VOICE_ID}", '
        f'prompt="{agent_prompt.replace(chr(34), chr(39))}". '
        f'Reply with ONLY a JSON object: {{"session_id": "<id>", "video_id": "<id>"}}'
    )
    response = client.beta.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        mcp_servers=[{"type": "url", "url": HEYGEN_MCP_URL, "name": "heygen",
                      "authorization_token": token}],
        messages=[{"role": "user", "content": prompt}],
        betas=["mcp-client-2025-04-04"],
    )
    # Buscar session_id y video_id en todos los bloques de la respuesta MCP
    haystack = ""
    for block in response.content:
        if hasattr(block, "text"):
            haystack += block.text + "\n"
        elif hasattr(block, "content") and isinstance(block.content, list):
            for sub in block.content:
                if hasattr(sub, "text"):
                    haystack += sub.text + "\n"

    session_match = re.search(r'"session_id"\s*:\s*"([^"]+)"', haystack)
    if not session_match:
        raise RuntimeError(f"No se pudo extraer session_id. Bloques MCP: {response.content}")
    session_id = session_match.group(1)

    match = re.search(r'"video_id"\s*:\s*"([^"]+)"', haystack)
    if not match:
        raise RuntimeError(f"No se pudo extraer video_id. Bloques MCP: {response.content}")
    return match.group(1), session_id


def esperar_video_heygen_mcp(session_id: str) -> str:
    """Espera a que el vídeo esté listo via MCP polling y devuelve la URL de descarga."""
    token = _leer_token_oauth_heygen()
    client = anthropic_sdk.Anthropic(api_key=cfg.anthropic_api_key)
    transcurrido = 0

    while transcurrido < POLL_TIMEOUT:
        prompt = (
            f'Call get_video_agent_session with session_id="{session_id}". '
            f'Reply with ONLY a JSON object: '
            f'{{"status": "<status>", "video_url": "<url_or_empty_string>"}}'
        )
        response = client.beta.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            mcp_servers=[{"type": "url", "url": HEYGEN_MCP_URL, "name": "heygen",
                          "authorization_token": token}],
            messages=[{"role": "user", "content": prompt}],
            betas=["mcp-client-2025-04-04"],
        )

        haystack = ""
        for block in response.content:
            if hasattr(block, "text"):
                haystack += block.text + "\n"
            elif hasattr(block, "content") and isinstance(block.content, list):
                for sub in block.content:
                    if hasattr(sub, "text"):
                        haystack += sub.text + "\n"

        status_match = re.search(r'"status"\s*:\s*"([^"]+)"', haystack)
        estado = status_match.group(1) if status_match else ""

        logger.info("session_id=%s → %s (%ds)", session_id, estado, transcurrido)

        if estado == "completed":
            url_match = re.search(r'"video_url"\s*:\s*"([^"]+)"', haystack)
            if url_match:
                return url_match.group(1)
            raise RuntimeError(
                f"Session completada pero sin video_url. Respuesta: {haystack}"
            )
        if estado in ("failed", "error"):
            raise RuntimeError(f"HeyGen falló: status={estado}. Respuesta: {haystack}")

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

            video_id, session_id = crear_video_heygen_mcp(texto, item["tema"])
            # Guarda el ID inmediatamente: si el proceso falla durante el polling
            # se puede retomar sabiendo qué job ya fue enviado.
            actualizar_fila(hoja, fila, {"ID_heygen": video_id})
            logger.info("Fila %d: job enviado — video_id=%s session_id=%s", fila, video_id, session_id)

            video_url = esperar_video_heygen_mcp(session_id)

            actualizar_fila(hoja, fila, {
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
