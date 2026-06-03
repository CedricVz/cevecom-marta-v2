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
import argparse
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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

HEYGEN_LOOK_ID = "5b39fad8d2254dd8aee6cf6b3f651ac5"  # portrait look validado por MCP
VOICE_ID       = "9d5fa6634a3a49c0bd9e47ec89a33dce"  # default_voice_id del nuevo look
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

ASSET_CATALOG = [
    # Citas / salón / ambiente
    {
        "label": "clienta cancelando cita",
        "url": "https://drive.google.com/file/d/1PQBac_pV9G-Jug7aD-Tv4df3iVd8oZpW/view",
        "asset_id": "2b6e926169ac42128d77b58c22826f45",
        "keywords": ["cita", "cancelar", "cancelando", "agenda", "avisar", "reloj", "tiempo"],
    },
    {
        "label": "silla vacía del salón",
        "url": "https://drive.google.com/file/d/1SLAD4rzNzd2oqvSzrA6lsDK8gD8cke0s/view",
        "asset_id": "79c691e646054dee862a41a4cd2275f1",
        "keywords": ["silla", "vacia", "vacía", "espacio vacio", "hora perdida"],
    },
    {
        "label": "clienta entrando al salón",
        "url": "https://drive.google.com/file/d/13I16KJWvzad5A-k2qDE9XOSn4QW6gr6W/view",
        "asset_id": "7c1375284c8344148865d255ea4a666d",
        "keywords": ["clienta entrando", "entrando", "entrada", "venir", "salon", "salón"],
    },
    {
        "label": "entrada del salón",
        "url": "https://drive.google.com/file/d/1WZsW22s1sCsD3w_MDUcdkK58dE3nkUM-/view",
        "asset_id": "6259d537750a4586aa99151f9435f6b3",
        "keywords": ["entrada", "salon", "salón", "centro", "local"],
    },
    {
        "label": "cabina estética facial",
        "url": "https://drive.google.com/file/d/110uc_-p2PTj3b2Mo4vbUK6ed6K7iGmkw/view",
        "asset_id": "bf6dad91df4f4033b53774bba285a1ee",
        "keywords": ["cabina estetica", "cabina estética", "cabina facial"],
    },
    {
        "label": "cabina final grande",
        "url": "",
        "asset_id": "ea7d5ceaaf0c42ff90269a8b803daf9f",
        "keywords": ["cabina", "salon", "salón", "centro", "local", "ambiente"],
    },
    # Tratamientos faciales / producto
    {
        "label": "producto botox",
        "url": "https://drive.google.com/file/d/1Y9kua_KV130j8PKtdNcKsHOMi7cJyoQc/view",
        "asset_id": "14e7a1335155453e9e4e0f1104b550ce",
        "keywords": ["producto botox", "botox", "producto"],
    },
    {
        "label": "tratamiento botox",
        "url": "https://drive.google.com/file/d/14hVIlEiPdpOTXCerhVaTjKFpgpryjy45/view",
        "asset_id": "77cf57d6bc8345028a55e40664c211e6",
        "keywords": ["tratamiento botox", "botox capilar", "botox"],
    },
    {
        "label": "aplicar crema facial",
        "url": "https://drive.google.com/file/d/1YddOcZLToTJb18nn5sZBLxiKvtsFk2Pl/view",
        "asset_id": "2008ba45158e443e9bce1d76fdbacb24",
        "keywords": ["aplicar crema", "crema facial", "video facial", "facial"],
    },
    {
        "label": "masaje facial",
        "url": "https://drive.google.com/file/d/1rUU2QvUfWeBiy6WeL-GKcFDY3GtyQT2G/view",
        "asset_id": "4e143bc564264691a73c282251114a57",
        "keywords": ["masaje facial", "video facial", "facial"],
    },
    {
        "label": "vapor facial",
        "url": "",
        "asset_id": "049f8ff84b8c4296bcfe284e4007e407",
        "keywords": ["vapor facial", "video facial", "facial", "limpieza facial"],
    },
    {
        "label": "radiofrecuencia facial",
        "url": "https://drive.google.com/file/d/1raaXNG8JGjHVCMPy6GA259tWbEi6iSpY/view",
        "asset_id": "cb2abb401c9547f4af6166d90e1c3629",
        "keywords": ["radiofrecuencia", "reafirmar", "colageno", "colágeno"],
    },
    {
        "label": "laser",
        "url": "https://drive.google.com/file/d/144eXxhI66cA6TnEtrDUZrrwjdBIjT0mt/view",
        "asset_id": "972ba0fdaa5b46c38737f443a41b1a7e",
        "keywords": ["laser", "láser", "depilacion", "depilación"],
    },
    # Corporales
    {
        "label": "drenaje abdomen",
        "url": "https://drive.google.com/file/d/1W7vG3qxAxnyPPSJr-ZPsUDQNvCmImkqC/view",
        "asset_id": "21665fb6f6b741ab80b9c4b991d6ff54",
        "keywords": ["drenaje", "abdomen", "retencion", "retención", "linfatico", "linfático", "hifu barriga", "hifu abdomen", "reafirmar abdomen", "corporal"],
    },
    {
        "label": "barriga inchada",
        "url": "",
        "asset_id": "6516ec3496e046c1bb05bf5a02c9b96f",
        "keywords": ["barriga", "abdomen", "hinchada", "inchada", "retencion", "retención", "hifu barriga", "hifu abdomen", "reafirmar", "flacidez abdomen"],
    },
    {
        "label": "maderoterapia en camilla",
        "url": "https://drive.google.com/file/d/1zZqBq18SgdEm0JWRMPwWcibEAzk0Q5AV/view",
        "asset_id": "1e0485d62d5041ccb964d18459ed7c53",
        "keywords": ["maderoterapia", "madero", "rodillos", "celulitis", "piernas", "hifu piernas", "reafirmar piernas", "corporal"],
    },
    {
        "label": "maderoterapia glúteos",
        "url": "https://drive.google.com/file/d/1GUDCL6Zskts3iwZiKlgBPfGl41RIhcVr/view",
        "asset_id": "ad48e5ffd889461f96798d9fe26b3256",
        "keywords": ["maderoterapia", "madero", "gluteos", "glúteos", "celulitis", "piernas", "hifu piernas", "flacidez piernas"],
    },
    {
        "label": "maderoterapia culo",
        "url": "",
        "asset_id": "2e16e2de9edb4e1d891bb488ed437fe5",
        "keywords": ["maderoterapia", "madero", "gluteos", "glúteos", "culo", "celulitis", "piernas", "hifu piernas", "flacidez piernas"],
    },
    {
        "label": "HIFU brazos",
        "url": "https://drive.google.com/file/d/1IIq5uLQXEiCoot_5xnI3hc_gz7a0PsLT/view",
        "asset_id": "029ff6c1f53546f2b79a0fc194e7f08f",
        "keywords": ["hifu", "hyfu", "brazos", "flacidez", "hifu brazos", "hifu corporal", "reafirmar"],
    },
    # Pelo
    {
        "label": "lavar cabeza",
        "url": "https://drive.google.com/file/d/1Ka9_0u49GaVL5rSl-qz-_xtg_czZBVeL/view",
        "asset_id": "df2368f300a14cfcbeaf0b70ee56f3b7",
        "keywords": ["lavar cabeza", "champu", "champú", "cabello", "pelo"],
    },
    {
        "label": "video keratina",
        "url": "https://drive.google.com/file/d/1Ukn_EzIKxAtez_mV0xkLBjoj9g5Kmi-8/view",
        "asset_id": "aee7d7d68d974ba4bcf88ae819fe8a0f",
        "keywords": ["keratina", "cabello", "pelo"],
    },
    {
        "label": "balayage",
        "url": "https://drive.google.com/file/d/191Lq8QKnfPaYusoWyc6AG9kQv1duD8_T/view",
        "asset_id": "b4504c405b18432cbf53744f523516ac",
        "keywords": ["balayage", "babylights", "rubio", "color", "pelo", "cabello"],
    },
]

POLL_INTERVALO = 60    # segundos entre checks de estado
POLL_TIMEOUT   = 1800   # 30 minutos máximo por vídeo


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera vídeos en HeyGen desde JSON por stdin.")
    parser.add_argument(
        "--dry-run-assets",
        action="store_true",
        help="Solo muestra qué B-roll seleccionaría para cada item; no llama a HeyGen ni Sheets.",
    )
    parser.add_argument(
        "--no-broll-files",
        action="store_true",
        help="No adjunta B-roll como files a HeyGen; mantiene las instrucciones en el prompt.",
    )
    return parser.parse_args()


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
    t = _normalizar(titulo)
    for key in ASSET_URLS:
        if _normalizar(key) in t:
            return ASSET_URLS[key]
    return ASSET_URLS["default"]


def _normalizar(s: str) -> str:
    sin_acentos = ''.join(
        c for c in unicodedata.normalize('NFD', s.lower())
        if unicodedata.category(c) != 'Mn'
    )
    return re.sub(r"\s+", " ", sin_acentos).strip()


def _seleccionar_broll(item: dict, max_assets: int = 12) -> list[dict[str, str]]:
    texto_busqueda = _normalizar(" ".join([
        item.get("tema", ""),
        item.get("tratamiento", ""),
        item.get("audiencia", ""),
        item.get("notas_escenas", ""),
    ]))
    candidatos = []
    vistos = set()

    for orden, asset in enumerate(ASSET_CATALOG):
        if asset["url"] in vistos:
            continue
        coincidencias = [
            keyword for keyword in asset["keywords"]
            if _normalizar(keyword) in texto_busqueda
        ]
        if coincidencias:
            candidatos.append((len(coincidencias), orden, asset))
            vistos.add(asset["url"])

    candidatos.sort(key=lambda item: (-item[0], item[1]))
    seleccionados = [
        {
            "label": asset["label"],
            "url": asset["url"],
            **({"asset_id": asset["asset_id"]} if asset.get("asset_id") else {}),
        }
        for _, _, asset in candidatos[:max_assets]
    ]

    if not seleccionados:
        seleccionados.append({
            "label": "B-roll principal por tratamiento",
            "url": _asset_url_para_tratamiento(item.get("tema", "")),
        })
    return seleccionados


def _bloque_broll_assets(assets: list[dict[str, str]]) -> str:
    lines = [
        "AVAILABLE REAL B-ROLL ASSETS (use these exact clips when relevant; do not use generic stock footage):"
    ]
    for idx, asset in enumerate(assets, start=1):
        lines.append(f"{idx}. {asset['label']}: {asset['url']}")
    return "\n".join(lines)


def _drive_url_descarga(url: str) -> str:
    match = re.search(r"/file/d/([^/]+)/", url)
    if match:
        return f"https://drive.google.com/uc?export=download&id={match.group(1)}"

    parsed = urlparse(url)
    file_id = parse_qs(parsed.query).get("id", [""])[0]
    if "drive.google.com" in parsed.netloc and file_id:
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    return url


def _files_para_video_agent(assets: list[dict[str, str]]) -> list[dict[str, str]]:
    files = []
    for asset in assets:
        if asset.get("asset_id"):
            files.append({"type": "asset_id", "asset_id": asset["asset_id"]})
            continue

        logger.warning(
            "B-roll omitido porque aún no tiene asset_id de HeyGen: %s",
            asset["label"],
        )
    return files


def _url_descarga_video_directo(url: str) -> bool:
    try:
        response = requests.get(url, stream=True, allow_redirects=True, timeout=20)
        content_type = response.headers.get("Content-Type", "").lower()
        first_chunk = next(response.iter_content(16), b"")
        response.close()
    except requests.RequestException as e:
        logger.warning("No se pudo validar B-roll %s: %s", url, e)
        return False

    if response.status_code != 200:
        return False
    if first_chunk.startswith(b"<!DOCTYPE") or first_chunk.startswith(b"<html"):
        return False
    return "video" in content_type or "octet-stream" in content_type


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


def crear_video_heygen_mcp(
    texto: str,
    titulo: str,
    notas_escenas: str = "",
    broll_context: dict | None = None,
    adjuntar_broll_files: bool = True,
) -> str:
    """Crea el vídeo via Video Agent MCP (~6 créditos, plan web) y devuelve session_id.

    El video_id no está disponible al crear — se obtiene al final del polling
    en `esperar_video_heygen_mcp` (que también devuelve la URL).
    """
    token = _leer_token_oauth_heygen()
    item_context = {"tema": titulo, "notas_escenas": notas_escenas, **(broll_context or {})}
    broll_assets = _seleccionar_broll(item_context)
    broll_block = _bloque_broll_assets(broll_assets)
    broll_files = _files_para_video_agent(broll_assets) if adjuntar_broll_files else []
    if not adjuntar_broll_files:
        logger.warning("B-roll files desactivados: HeyGen recibirá solo instrucciones en el prompt.")
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
        f"CRITICAL SCRIPT REQUIREMENT: Do not summarize, rewrite, shorten, "
        f"skip, reorder, or remove any spoken sentence. The avatar voice "
        f"must say the full script word for word, even if the final video "
        f"becomes longer than planned. "
        f"AVATAR FRAMING: Place avatar {HEYGEN_LOOK_ID} as a portrait "
        f"talking head — crop and frame to show face and upper body "
        f"centered in a vertical 9:16 composition. The avatar source "
        f"is landscape but the OUTPUT must be portrait. "
        f"Use voice ID {VOICE_ID}. "
        f"Brand colors: {BRAND_COLORS}. Apply to text overlays and "
        f"graphic elements. Brand kit ID: {BRAND_KIT_ID}. "
        f"TEXT OVERLAY RULES: Do not add continuous subtitles/captions "
        f"for every spoken sentence. Use only short, intentional on-screen "
        f"text overlays requested by the scene direction or useful for hooks "
        f"and CTA. Text must be highly legible on mobile: bold white text "
        f"on a dark translucent background or brand red/gold solid label, "
        f"with enough contrast and safe margins. Never place pale text "
        f"directly over bright footage. "
        f"VIDEO STRUCTURE: "
        f"Open with avatar talking head, beauty clinic background, "
        f"warm professional lighting, portrait framing. "
        f"Then keep the avatar voice reading the complete script and "
        f"intercut with real footage from the center. {broll_block} "
        f"Show hands-on treatment, professional equipment, actual clinic space, "
        f"or appointment-related clips according to the scene direction. "
        f"NO generic stock footage. "
        f"All B-roll must be portrait 9:16. "
        f"Timing is flexible: prioritize the complete spoken script over "
        f"the target duration. "
        f"[35-45s] Avatar delivers CTA, 'Marta Suñé' branding visible. "
        f"If the CTA happens after 45 seconds because the script is longer, "
        f"that is correct. Do not cut the script to fit any timestamp. "
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
        "files": broll_files or None,
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
    args = parse_args()
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

    if args.dry_run_assets:
        preview = [
            {
                "fila": item.get("fila"),
                "marta_fila": item.get("marta_fila"),
                "tema": item.get("tema"),
                "broll_assets": _seleccionar_broll(item),
                "files_payload": _files_para_video_agent(_seleccionar_broll(item)),
            }
            for item in guiones
        ]
        print(json.dumps(preview, ensure_ascii=False, indent=2))
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
                texto,
                item["tema"],
                notas_escenas=item.get("notas_escenas", ""),
                broll_context=item,
                adjuntar_broll_files=not args.no_broll_files,
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
