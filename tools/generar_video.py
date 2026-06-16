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

HEYGEN_LOOK_ID = "447c12c04e8b44678da17c881fbc7476"  # Look 1 principal aprobado
HEYGEN_LOOK_2_ID = "19c92f39df754582a642aa0a872e46b0"  # Look 2 secundario, uso manual por Look_ID
VOICE_ID       = "9d5fa6634a3a49c0bd9e47ec89a33dce"  # default_voice_id de Look 1 y Look 2
BRAND_COLORS   = "#D71F28 (rojo), #C5A059 (dorado), #605E5E (gris), #FFFFFF"
CENTRO_DIR     = "C/ Munné 15-17 bajos, Barcelona"
BRAND_KIT_ID   = "bf6988fde35849079d09f9a6fa5b092d"
HEYGEN_LOGO_ASSET_ID = "f51d0994f8fe4af9876fa5725df111f9"

PATRONES_TTS_MARKUP_PROHIBIDOS = (
    "<break",
    "/>",
    "<",
    ">",
    "time=",
    "quote",
    "slash",
    "greater than",
    "less than",
    "ssml",
    "xml",
)

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
        "asset_id": "0fea4209c90e47d69689d186fb1950e3",
        "keywords": ["cita", "cancelar", "cancelando", "agenda", "avisar", "reloj", "tiempo"],
    },
    {
        "label": "silla vacía del salón",
        "url": "https://drive.google.com/file/d/1SLAD4rzNzd2oqvSzrA6lsDK8gD8cke0s/view",
        "asset_id": "c7e220e88be2498ea9bbcc2471bd5c7e",
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
        "asset_id": "b90e48a00e11430c9bc3d96f19c0ec29",
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
        "asset_id": "f813f53a7bf24d61b00b56ec2d3b8215",
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
        "asset_id": "7582bf963cb4493f90640201cfcea405",
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
        "--dry-run-prompt",
        action="store_true",
        help="Muestra el prompt final para HeyGen; no llama a HeyGen ni Sheets.",
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


def _limpiar_texto_para_tts(texto: str) -> str:
    """Elimina emojis del texto hablado sin cambiar palabras ni puntuación normal."""
    limpio = "".join(
        c for c in texto
        if not (
            "\U0001F000" <= c <= "\U0001FAFF"
            or "\U00002700" <= c <= "\U000027BF"
            or "\U00002600" <= c <= "\U000026FF"
        )
    )
    lineas = [re.sub(r"[ \t]{2,}", " ", linea).strip() for linea in limpio.splitlines()]
    limpio = "\n".join(linea for linea in lineas)
    limpio = re.sub(r"\n{3,}", "\n\n", limpio)
    limpio = re.sub(r"[ \t]+([,.!?;:])", r"\1", limpio)
    return limpio.strip()


def _validar_texto_tts_sin_markup(texto: str) -> None:
    """Bloquea renders si el texto hablado contiene posible markup narrable."""
    texto_lower = texto.casefold()
    for patron in PATRONES_TTS_MARKUP_PROHIBIDOS:
        if patron in texto_lower:
            raise ValueError(
                "Texto hablado contiene posible markup técnico para HeyGen "
                f"(patrón detectado: {patron!r}). No se llama a HeyGen."
            )


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


def _contar_palabras(texto: str) -> int:
    return len(re.findall(r"\b\w+\b", texto, flags=re.UNICODE))


EXPLICIT_ASSET_REQUESTS = [
    {
        "solicitud": "agenda / cita",
        "terms": ["agenda abierta", "agenda", "cita reservada", "citas"],
        "labels": ["clienta cancelando cita"],
    },
    {
        "solicitud": "silla vacía",
        "terms": ["silla vacia", "silla vacía"],
        "labels": ["silla vacía del salón"],
    },
    {
        "solicitud": "reloj",
        "terms": ["reloj", "pasando las horas"],
        "labels": ["clienta cancelando cita"],
    },
    {
        "solicitud": "clienta entrando",
        "terms": ["clienta entrando", "entrando al salon", "entrando al salón", "video entrando al salon"],
        "labels": ["clienta entrando al salón"],
    },
    {
        "solicitud": "entrada",
        "terms": ["entrada", "entrada del salon", "entrada del salón"],
        "labels": ["entrada del salón"],
    },
    {
        "solicitud": "salón",
        "terms": ["salon", "salón", "centro", "local"],
        "labels": ["cabina final grande"],
    },
    {
        "solicitud": "cabina",
        "terms": ["cabina"],
        "labels": ["cabina final grande"],
    },
    {
        "solicitud": "maderoterapia",
        "terms": ["maderoterapia"],
        "labels": ["maderoterapia en camilla"],
    },
    {
        "solicitud": "HIFU",
        "terms": ["hifu", "hyfu"],
        "labels": ["HIFU brazos"],
    },
    {
        "solicitud": "láser",
        "terms": ["laser", "láser"],
        "labels": ["laser"],
    },
    {
        "solicitud": "aplicar crema facial",
        "terms": ["aplicar crema facial", "aplicar crema"],
        "labels": ["aplicar crema facial"],
    },
    {
        "solicitud": "masaje facial",
        "terms": ["masaje facial"],
        "labels": ["masaje facial"],
    },
    {
        "solicitud": "facial",
        "terms": ["video facial", "facial"],
        "labels": ["aplicar crema facial"],
    },
    {
        "solicitud": "balayage",
        "terms": ["balayage", "babylights"],
        "labels": ["balayage"],
    },
    {
        "solicitud": "producto botox",
        "terms": ["producto botox"],
        "labels": ["producto botox"],
    },
    {
        "solicitud": "drenaje",
        "terms": ["drenaje", "drenaje 4"],
        "labels": ["drenaje abdomen"],
    },
]


def _asset_por_label() -> dict[str, dict]:
    return {asset["label"]: asset for asset in ASSET_CATALOG}


def _asset_publico(asset: dict) -> dict[str, str]:
    return {
        "label": asset["label"],
        "url": asset["url"],
        **({"asset_id": asset["asset_id"]} if asset.get("asset_id") else {}),
    }


def _orden_presentacion(label: str) -> int:
    prioridad = {
        "clienta entrando al salón": 0,
        "entrada del salón": 1,
        "cabina final grande": 2,
        "cabina estética facial": 3,
    }
    return prioridad.get(label, 100)


def _orden_citas_cancelaciones(label: str) -> int:
    prioridad = {
        "clienta cancelando cita": 0,
        "silla vacía del salón": 1,
        "clienta entrando al salón": 2,
        "aplicar crema facial": 3,
        "drenaje abdomen": 4,
        "producto botox": 20,
    }
    return prioridad.get(label, 10)


def _es_reel_citas_cancelaciones(texto_busqueda: str) -> bool:
    return any(
        keyword in texto_busqueda
        for keyword in ["cancelar", "cancelacion", "cita", "agenda", "avisar", "silla vacia"]
    )


def _detectar_assets_solicitados(notas_escenas: str) -> tuple[list[dict], list[dict], list[str]]:
    texto_notas = _normalizar(notas_escenas)
    catalogo = _asset_por_label()
    solicitados = []
    encontrados = []
    no_encontrados = []

    for rule_index, rule in enumerate(EXPLICIT_ASSET_REQUESTS):
        posiciones = [
            texto_notas.find(_normalizar(term))
            for term in rule["terms"]
            if _normalizar(term) in texto_notas
        ]
        if not posiciones:
            continue
        posicion = min(posiciones)
        solicitud = rule["solicitud"]
        solicitados.append(solicitud)
        asset = next((catalogo.get(label) for label in rule["labels"] if catalogo.get(label)), None)
        if not asset:
            no_encontrados.append(solicitud)
            continue
        encontrados.append({
            "solicitud": solicitud,
            "label": asset["label"],
            "asset": asset,
            "posicion": posicion,
            "rule_index": rule_index,
            "presentacion_order": _orden_presentacion(asset["label"]),
        })

    return solicitados, encontrados, no_encontrados


def _clasificar_tipo_reel(item: dict, texto: str) -> str:
    texto_busqueda = _normalizar(" ".join([
        item.get("tema", ""),
        item.get("tratamiento", ""),
        item.get("notas_escenas", ""),
        texto,
    ]))
    keywords_presentacion = [
        "clon",
        "version digital",
        "atencion 24/7",
        "atencion personalizada 24/7",
        "bienvenida",
        "presentacion",
        "anuncio",
        "mensaje directo",
        "dm",
        "nunca te quedes sin respuesta",
    ]
    if any(keyword in texto_busqueda for keyword in keywords_presentacion):
        return "presentacion_clon"
    return "reel_estandar"


def _max_broll_assets_para_item(item: dict, texto: str) -> int:
    solicitados, encontrados, _no_encontrados = _detectar_assets_solicitados(
        item.get("notas_escenas", "")
    )
    if solicitados:
        return max(len(encontrados), len(solicitados), 1)
    return 6 if _contar_palabras(texto) > 130 else 4


def _normalizar_notas_escenas(notas: str, tipo_reel: str) -> str:
    if not notas:
        return ""

    estilo_overlay_ignorado = {
        "estilo texto",
        "color blanco",
        "blanco",
        "efecto escribiendose",
        "minimalista",
        "parte inferior",
        "parte inferior del video",
        "estilo",
        "centro pantalla",
        "misma posicion y estilo del texto inicial",
    }
    lineas_limpias = []
    for linea in notas.splitlines():
        clave = _normalizar(linea).strip(" .:")
        if clave in estilo_overlay_ignorado:
            continue
        if clave.startswith("efecto escrib") or clave.startswith("misma posici"):
            continue
        if clave.startswith("mismo estilo"):
            continue
        lineas_limpias.append(linea)
    notas_limpias = "\n".join(lineas_limpias)

    reglas = [
        "NORMALIZED SCENE DIRECTION RULES:",
        "Respect Marta's creative intention, tone, scene order, visual resources, and requested B-roll.",
        "Interpret any instruction such as PONER TEXTO, TEXTO GRANDE, CENTRO PANTALLA, EFECTO ESCRIBIENDOSE, TEXTOS UNO A UNO, LABELS, or TITULOS as subtitle intent only, not as decorative overlays.",
        "Convert suggested text into simple native subtitles at bottom center, maximum two lines, and one caption block at a time.",
        "Do not create creative title cards, floating labels, text lists, center-screen text, or extra decorative copy.",
    ]
    if tipo_reel == "presentacion_clon":
        reglas.extend([
            "For this presentation/clon reel, Marta's avatar is the narrative protagonist.",
            "Use B-roll as support for Marta's story, following the specific assets Marta requested.",
            "If Marta requested treatment clips, use them intentionally and keep transitions coherent rather than suppressing them.",
        ])

    return "\n".join(reglas) + "\n\nORIGINAL SCENE DIRECTION FROM MARTA:\n" + notas_limpias


def _resolver_look_voice(item: dict) -> tuple[str, str]:
    look_solicitado = (item.get("look_id") or item.get("Look_ID") or "").strip()
    if look_solicitado == HEYGEN_LOOK_2_ID:
        return HEYGEN_LOOK_2_ID, VOICE_ID
    if look_solicitado and look_solicitado != HEYGEN_LOOK_ID:
        logger.warning(
            "Look_ID %s no está permitido como look del sistema; se usará Look 1.",
            look_solicitado,
        )
    return HEYGEN_LOOK_ID, VOICE_ID


def _seleccionar_broll(
    item: dict,
    max_assets: int = 12,
    tipo_reel: str = "reel_estandar",
) -> list[dict[str, str]]:
    return _seleccionar_broll_detallado(item, max_assets=max_assets, tipo_reel=tipo_reel)["assets_finales"]


def _seleccionar_broll_detallado(
    item: dict,
    max_assets: int = 12,
    tipo_reel: str = "reel_estandar",
) -> dict:
    texto_busqueda = _normalizar(" ".join([
        item.get("tema", ""),
        item.get("tratamiento", ""),
        item.get("audiencia", ""),
        item.get("notas_escenas", ""),
        item.get("guion", ""),
    ]))
    candidatos_heuristica = []
    vistos = set()

    for orden, asset in enumerate(ASSET_CATALOG):
        if asset["url"] in vistos:
            continue
        coincidencias = [
            keyword for keyword in asset["keywords"]
            if _normalizar(keyword) in texto_busqueda
        ]
        if coincidencias:
            candidatos_heuristica.append((len(coincidencias), orden, asset))
            vistos.add(asset["url"])

    candidatos_heuristica.sort(key=lambda item: (-item[0], item[1]))
    solicitados, encontrados, no_encontrados = _detectar_assets_solicitados(
        item.get("notas_escenas", "")
    )
    motivo_seleccion = []
    warnings = []
    seleccionados_assets = []
    labels_seleccionados = set()
    fallback_assets = []

    if encontrados:
        motivo_seleccion.append("Se priorizan assets pedidos explícitamente por Marta en notas_escenas.")
    if no_encontrados:
        motivo_seleccion.append("Algunas solicitudes de Marta no existen en el catálogo y se cubrirán con fallback.")
    if len(encontrados) > 4:
        warnings.append(
            f"Marta pidió {len(encontrados)} assets; esto puede aumentar duración/coste o generar un vídeo más cargado."
        )

    def agregar(asset: dict, motivo: str) -> bool:
        if asset["label"] in labels_seleccionados:
            return False
        seleccionados_assets.append(asset)
        labels_seleccionados.add(asset["label"])
        if motivo == "fallback":
            fallback_assets.append(asset)
        return True

    if tipo_reel == "presentacion_clon":
        prioridad_presentacion_core = {
            "clienta entrando al salón": 0,
            "entrada del salón": 1,
            "cabina final grande": 2,
            "cabina estética facial": 3,
        }
        prioridad_presentacion_fallback = {
            "aplicar crema facial": 4,
            "masaje facial": 5,
        }
        prioridad_presentacion = {
            **prioridad_presentacion_core,
            **prioridad_presentacion_fallback,
        }
        encontrados_ordenados = sorted(encontrados, key=lambda entry: (entry["posicion"], entry["rule_index"]))
        for entry in encontrados_ordenados:
            agregar(entry["asset"], "marta")

        if not encontrados or no_encontrados:
            for _orden, asset in enumerate(ASSET_CATALOG):
                label = asset["label"]
                if label not in prioridad_presentacion_core or label in labels_seleccionados:
                    continue
                if len(seleccionados_assets) >= max_assets:
                    break
                if agregar(asset, "fallback"):
                    labels_seleccionados.add(label)
        if fallback_assets:
            motivo_seleccion.append("Se completa con salón/cabina/entrada como fallback de coherencia.")
    else:
        if _es_reel_citas_cancelaciones(texto_busqueda) and not encontrados:
            motivo_seleccion.append(
                "Para reel de citas/cancelaciones sin assets explícitos se priorizarán cita, silla vacía y entrada como fallback."
            )
        encontrados_ordenados = sorted(encontrados, key=lambda item: (item["posicion"], item["rule_index"]))
        for entry in encontrados_ordenados:
            agregar(entry["asset"], "marta")
        if not encontrados:
            for _, _, asset in candidatos_heuristica[:max_assets]:
                agregar(asset, "heuristica")
        elif len(encontrados) < max_assets and no_encontrados:
            for _, _, asset in candidatos_heuristica:
                if len(seleccionados_assets) >= max_assets:
                    break
                agregar(asset, "fallback")

    if not seleccionados_assets:
        if tipo_reel == "presentacion_clon":
            for asset in ASSET_CATALOG:
                if asset["label"] in prioridad_presentacion:
                    agregar(asset, "fallback")
            motivo_seleccion.append("No hubo coincidencias; se usa fallback visual de presentación.")
        else:
            seleccionados_assets.append({
                "label": "B-roll principal por tratamiento",
                "url": _asset_url_para_tratamiento(item.get("tema", "")),
            })
            motivo_seleccion.append("No hubo coincidencias; se usa B-roll por tratamiento como fallback.")

    assets_finales = [_asset_publico(asset) for asset in seleccionados_assets]
    return {
        "assets_solicitados_por_marta": solicitados,
        "assets_encontrados": [
            {
                "solicitud": entry["solicitud"],
                "label": entry["label"],
                **({"asset_id": entry["asset"]["asset_id"]} if entry["asset"].get("asset_id") else {}),
            }
            for entry in encontrados
        ],
        "assets_no_encontrados": no_encontrados,
        "assets_fallback": [_asset_publico(asset) for asset in fallback_assets],
        "assets_finales": assets_finales,
        "motivo_seleccion": motivo_seleccion,
        "warnings": warnings,
    }


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


def _preparar_video_agent_payload(
    texto: str,
    titulo: str,
    notas_escenas: str = "",
    broll_context: dict | None = None,
    adjuntar_broll_files: bool = True,
) -> dict:
    texto_tts = _limpiar_texto_para_tts(texto)
    _validar_texto_tts_sin_markup(texto_tts)
    item_context = {"tema": titulo, "notas_escenas": notas_escenas, **(broll_context or {})}
    tipo_reel = _clasificar_tipo_reel(item_context, texto_tts)
    max_broll_assets = _max_broll_assets_para_item(item_context, texto_tts)
    broll_selection = _seleccionar_broll_detallado(
        item_context,
        max_assets=max_broll_assets,
        tipo_reel=tipo_reel,
    )
    broll_assets = broll_selection["assets_finales"]
    broll_block = _bloque_broll_assets(broll_assets)
    broll_files = _files_para_video_agent(broll_assets) if adjuntar_broll_files else []
    if not adjuntar_broll_files:
        logger.warning("B-roll files desactivados: HeyGen recibirá solo instrucciones en el prompt.")
    notas_normalizadas = _normalizar_notas_escenas(notas_escenas, tipo_reel)
    scene_direction = (
        f"SCENE DIRECTION (follow exactly):\n{notas_normalizadas}\n\n"
        if notas_normalizadas else ""
    )
    avatar_id, voice_id = _resolver_look_voice(item_context)
    first_words_rule = (
        'The first spoken words must be exactly: "Hola, soy Marta." '
        if texto_tts.strip().startswith("Hola, soy Marta.")
        else "The first spoken words must be exactly the first words of the script. "
    )
    agent_prompt = (
        f"Create a 9:16 VERTICAL portrait Instagram Reel "
        f"(720x1280px) for 'Marta Suñé Estilista "
        f"& Estética Avanzada', a premium beauty center in Barcelona "
        f"at {CENTRO_DIR}. "
        f"TARGET DURATION: 50-58 seconds. The video may be slightly longer "
        f"only if needed to complete the full script naturally. Never slow "
        f"down the voice to fill time. Never cut the script. "
        f"CRITICAL OUTPUT REQUIREMENT: The final video MUST be vertical "
        f"9:16 portrait format. "
        f"CRITICAL SCRIPT REQUIREMENT: Do not summarize, rewrite, shorten, "
        f"skip, reorder, or remove any spoken sentence. The avatar voice "
        f"must say the full script word for word, even if the final video "
        f"becomes longer than planned. {first_words_rule}"
        f"Do not say any filler, interjection, 'qué', 'eh', 'bueno', "
        f"or any word before the script. Use a natural, fluent "
        f"conversational Spanish pace. Do not artificially slow down the "
        f"narration to fill the target duration. Use short natural pauses only. "
        f"AVATAR FRAMING: Place avatar {avatar_id} as a portrait "
        f"talking head — crop and frame to show face and upper body "
        f"centered in a vertical 9:16 composition. The avatar source "
        f"is landscape but the OUTPUT must be portrait. "
        f"Use voice ID {voice_id}. "
        f"Brand colors: {BRAND_COLORS}. Brand kit ID: {BRAND_KIT_ID}. "
        f"NARRATION SEPARATION - FOLLOW EXACTLY: "
        f"SPOKEN SCRIPT — ONLY THIS TEXT MAY BE SPOKEN. "
        f"VISUAL INSTRUCTIONS — NEVER NARRATE THESE INSTRUCTIONS. "
        f"Only the final SPOKEN SCRIPT block may be spoken by the avatar. "
        f"All policies, scene notes, timing notes, and "
        f"asset directions are visual instructions and must never be narrated. "
        f"NATIVE SUBTITLES POLICY - FOLLOW EXACTLY: "
        f"Use HeyGen native subtitles/captions if available. Keep them simple, "
        f"clean, bottom centered, highly legible on mobile, synchronized with "
        f"the spoken voice, maximum two lines at a time. Use a neutral/native "
        f"caption style, not a designed gold box, not animated typography, and "
        f"not decorative text overlays. Do not create floating quotes, "
        f"center-screen titles, animated title cards, service labels, duplicated "
        f"phrases, kinetic typography, extra marketing copy, bands, boxes, "
        f"large titles, or duplicate spoken text anywhere else on screen. "
        f"If Marta's scene notes ask for PONER TEXTO, TEXTO GRANDE, "
        f"CENTRO PANTALLA, EFECTO ESCRIBIENDOSE, TEXTOS UNO A UNO, labels, "
        f"or treatment names, interpret that only as subtitle intent or ignore "
        f"it when it duplicates the spoken script. Captions must match the "
        f"spoken sentence and must not compete with Marta's face. "
        f"NO LOGO OR OUTRO POLICY - FOLLOW EXACTLY: "
        f"Do not add a logo, final slate, outro, end card, or closing scene. "
        f"The final brand slate will be added after approval by a separate "
        f"postproduction step. Do not show brand logos, logo placeholders, "
        f"final screens, end screens, closing cards, or extra closing visuals. "
        f"VIDEO STRUCTURE: "
        f"Open with avatar talking head, beauty clinic background, "
        f"warm professional lighting, portrait framing. "
        f"Then keep the avatar voice reading the complete script and "
        f"intercut with real footage from the center. {broll_block} "
        f"Show hands-on treatment, professional equipment, actual clinic space, "
        f"or appointment-related clips according to the scene direction. "
        f"NO generic stock footage. "
        f"All B-roll must be portrait 9:16. "
        f"B-roll must support the message without competing with captions "
        f"or the final CTA. If the scene direction asks for extra text, "
        f"large titles, treatment lists, floating labels, or decorative copy, "
        f"ignore those text overlay requests and follow the NATIVE SUBTITLES "
        f"POLICY instead. "
        f"VISUAL SAFETY: "
        f"Never create black screens, black rectangles, empty placeholders, "
        f"missing media blocks, blank scenes, or visual gaps. Every second must "
        f"contain the avatar, an approved B-roll asset, or a clean branded "
        f"background. "
        f"ENDING POLICY - FOLLOW EXACTLY: "
        f"Do not cut the final sentence. Do not add any spoken or visual "
        f"material after the script ends. Do not add spoken words, captions, "
        f"markup, SSML, XML, timing tags, extra narration, logo, outro, final "
        f"slate, end card, or closing scene. Do not end on an empty screen, "
        f"generic background, placeholder, or black frame. "
        f"STYLE: warm, professional, approachable. "
        f"{scene_direction}"
        f"SPOKEN SCRIPT — ONLY THIS TEXT MAY BE SPOKEN:\n\n{texto_tts}"
    )
    return {
        "mode": "generate",
        "orientation": "portrait",
        "avatarId": avatar_id,
        "voiceId": voice_id,
        "brandKitId": BRAND_KIT_ID,
        "files": broll_files or None,
        "prompt": agent_prompt,
        "tipo_reel": tipo_reel,
        "palabras_guion_hablado": _contar_palabras(texto_tts),
        "emojis_eliminados_tts": texto_tts != texto,
        "guion_tts_limpio": texto_tts,
        "max_broll_assets": max_broll_assets,
        "broll_assets": broll_assets,
        "broll_selection": broll_selection,
        "warnings": broll_selection["warnings"],
    }


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
    payload = _preparar_video_agent_payload(
        texto,
        titulo,
        notas_escenas=notas_escenas,
        broll_context=broll_context,
        adjuntar_broll_files=adjuntar_broll_files,
    )
    token = _leer_token_oauth_heygen()
    result = _llamar_mcp_heygen("create_video_agent", {
        "mode": payload["mode"],
        "orientation": payload["orientation"],
        "avatarId": payload["avatarId"],
        "voiceId": payload["voiceId"],
        "brandKitId": payload["brandKitId"],
        "files": payload["files"],
        "prompt": payload["prompt"],
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
        preview = []
        for item in guiones:
            texto = extraer_texto_hablado(item.get("guion", ""))
            texto_tts = _limpiar_texto_para_tts(texto)
            tipo_reel = _clasificar_tipo_reel(item, texto_tts)
            max_broll_assets = _max_broll_assets_para_item(item, texto_tts)
            broll_selection = _seleccionar_broll_detallado(
                item,
                max_assets=max_broll_assets,
                tipo_reel=tipo_reel,
            )
            broll_assets = broll_selection["assets_finales"]
            preview.append({
                "fila": item.get("fila"),
                "marta_fila": item.get("marta_fila"),
                "tema": item.get("tema"),
                "tipo_reel": tipo_reel,
                "palabras_guion_hablado": _contar_palabras(texto_tts),
                "emojis_eliminados_tts": texto_tts != texto,
                "max_broll_assets": max_broll_assets,
                "assets_solicitados_por_marta": broll_selection["assets_solicitados_por_marta"],
                "assets_encontrados": broll_selection["assets_encontrados"],
                "assets_no_encontrados": broll_selection["assets_no_encontrados"],
                "assets_fallback": broll_selection["assets_fallback"],
                "assets_finales": broll_selection["assets_finales"],
                "motivo_seleccion": broll_selection["motivo_seleccion"],
                "warnings": broll_selection["warnings"],
                "broll_assets": broll_assets,
                "files_payload": _files_para_video_agent(broll_assets),
            })
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return

    if args.dry_run_prompt:
        preview = []
        for item in guiones:
            texto = extraer_texto_hablado(item.get("guion", ""))
            payload = _preparar_video_agent_payload(
                texto,
                item.get("tema", ""),
                notas_escenas=item.get("notas_escenas", ""),
                broll_context=item,
                adjuntar_broll_files=not args.no_broll_files,
            )
            preview.append({
                "fila": item.get("fila"),
                "marta_fila": item.get("marta_fila"),
                "tema": item.get("tema"),
                "tipo_reel": payload["tipo_reel"],
                "palabras_guion_hablado": payload["palabras_guion_hablado"],
                "emojis_eliminados_tts": payload["emojis_eliminados_tts"],
                "guion_tts_limpio": payload["guion_tts_limpio"],
                "max_broll_assets": payload["max_broll_assets"],
                "avatarId": payload["avatarId"],
                "voiceId": payload["voiceId"],
                "brandKitId": payload["brandKitId"],
                "orientation": payload["orientation"],
                "broll_assets": payload["broll_assets"],
                "broll_selection": payload["broll_selection"],
                "warnings": payload["warnings"],
                "files": payload["files"],
                "prompt": payload["prompt"],
            })
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
