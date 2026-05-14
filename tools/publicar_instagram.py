"""
tools/publicar_instagram.py — Publica en Instagram los Reels aprobados por Marta.

Lee Google Sheets directamente buscando filas con Estado="Aprobado",
sube cada vídeo a Instagram vía Meta Graph API y actualiza la hoja
con la URL y fecha de publicación.

No recibe stdin. Se ejecuta de forma independiente, normalmente
en el mismo cron que el pipeline de generación, para procesar
las aprobaciones acumuladas desde la última ejecución.

Uso:
    python tools/publicar_instagram.py
"""

import json
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import gspread
from gspread.utils import rowcol_to_a1

from config import cfg
from tools._columnas import COL, CABECERAS
from tools.google_creds import service_account_credentials

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger("publicar_instagram")

SCOPES_WRITE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

META_API = "https://graph.instagram.com/v25.0"

# Hashtags que se añaden al final de cada caption.
HASHTAGS = "#cevecom #centroestética #belleza #barcelona #skincare #tratamientofacial"

POLL_INTERVALO = 10   # segundos entre checks de procesamiento en Meta
POLL_TIMEOUT   = 600  # 10 minutos máximo por vídeo


# ── Google Sheets ─────────────────────────────────────────────────────────────

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


def leer_aprobados(hoja: gspread.Worksheet) -> list[dict]:
    """Devuelve las filas con Estado='Aprobado' y Video_preview relleno."""
    filas = hoja.get_all_records(expected_headers=CABECERAS)
    aprobados = []
    for i, fila in enumerate(filas):
        if fila.get("Estado", "").strip() != "Aprobado":
            continue
        if not fila.get("Video_preview", "").strip():
            logger.warning(
                "Fila %d: Estado=Aprobado pero Video_preview vacío — se omite.", i + 2
            )
            continue
        aprobados.append({
            "fila":        i + 2,
            "tema":        fila["Tema"],
            "tratamiento": fila.get("Tratamiento", ""),
            "guion":       fila.get("Guion", ""),
            "video_url":   fila["Video_preview"],
        })
    return aprobados


# ── Caption ───────────────────────────────────────────────────────────────────

def construir_caption(item: dict) -> str:
    """Extrae el texto hablado del guión y añade los hashtags."""
    guion = item.get("guion", "").strip()
    if guion:
        texto = re.sub(r"\[.+?\]\n?", "", guion)
        texto = re.sub(r"\n{3,}", "\n\n", texto).strip()
    else:
        # Fallback si el guión no está en Sheets (fila aprobada manualmente)
        texto = item["tema"]

    return f"{texto}\n\n{HASHTAGS}" if HASHTAGS else texto


# ── Meta Graph API ────────────────────────────────────────────────────────────

def _meta_get(endpoint: str, **params) -> dict:
    r = requests.get(
        f"{META_API}/{endpoint}",
        params={"access_token": cfg.instagram_api_token, **params},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"Meta API error: {body['error']}")
    return body


def _meta_post(endpoint: str, **params) -> dict:
    r = requests.post(
        f"{META_API}/{endpoint}",
        params={"access_token": cfg.instagram_api_token, **params},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"Meta API error: {body['error']}")
    return body


def crear_contenedor(video_url: str, caption: str) -> str:
    """Crea el contenedor de vídeo en Instagram y devuelve su ID."""
    body = _meta_post(
        f"{cfg.instagram_user_id}/media",
        media_type="REELS",
        video_url=video_url,
        caption=caption,
    )
    return body["id"]


def esperar_procesamiento(container_id: str) -> None:
    """Espera a que Instagram procese el vídeo. Lanza excepción si falla."""
    transcurrido = 0
    while transcurrido < POLL_TIMEOUT:
        body   = _meta_get(container_id, fields="status_code")
        status = body.get("status_code", "")

        logger.info("container_id=%s → %s (%ds)", container_id, status, transcurrido)

        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Procesamiento de vídeo fallido: status={status}")

        time.sleep(POLL_INTERVALO)
        transcurrido += POLL_INTERVALO

    raise TimeoutError(f"Container {container_id} no procesado tras {POLL_TIMEOUT}s")


def publicar_contenedor(container_id: str) -> str:
    """Publica el contenedor y devuelve el media_id del post."""
    body = _meta_post(
        f"{cfg.instagram_user_id}/media_publish",
        creation_id=container_id,
    )
    return body["id"]


def obtener_permalink(media_id: str) -> str:
    """Devuelve la URL pública del Reel publicado."""
    body = _meta_get(media_id, fields="permalink")
    return body.get("permalink", f"https://www.instagram.com/reel/{media_id}/")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _registrar_error(hoja: gspread.Worksheet, fila: int, mensaje: str) -> None:
    reintentos = leer_reintentos(hoja, fila) + 1
    timestamp  = datetime.now().strftime("%Y-%m-%d %H:%M")
    actualizar_fila(hoja, fila, {
        "Estado":     "Error",
        "Errores":    f"{timestamp} | {mensaje}",
        "Reintentos": str(reintentos),
    })


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    try:
        hoja = conectar_sheets()
    except Exception as e:
        logger.error("Error conectando a Google Sheets: %s", e)
        sys.exit(1)

    aprobados = leer_aprobados(hoja)

    if not aprobados:
        logger.info("0 Reels aprobados pendientes de publicar.")
        print("[]")
        return

    logger.info("%d Reel(es) aprobado(s) para publicar.", len(aprobados))

    resultados = []

    for item in aprobados:
        fila = item["fila"]
        logger.info("Fila %d → publicando: %s", fila, item["tema"])

        try:
            caption      = construir_caption(item)
            container_id = crear_contenedor(item["video_url"], caption)
            logger.info("Fila %d: contenedor creado — %s", fila, container_id)

            esperar_procesamiento(container_id)

            media_id  = publicar_contenedor(container_id)
            permalink = obtener_permalink(media_id)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            actualizar_fila(hoja, fila, {
                "Estado":            "Publicado",
                "Fecha_publicacion": timestamp,
                "URL_instagram":     permalink,
                "Errores":           "",
            })

            resultados.append({**item, "url_instagram": permalink})
            logger.info("Fila %d: OK → %s", fila, permalink)

        except requests.HTTPError as e:
            logger.error("Fila %d: HTTP error Meta — %s", fila, e)
            _registrar_error(hoja, fila, f"Meta HTTP: {e}")

        except RuntimeError as e:
            logger.error("Fila %d: error Meta — %s", fila, e)
            _registrar_error(hoja, fila, str(e))

        except TimeoutError as e:
            logger.error("Fila %d: timeout — %s", fila, e)
            _registrar_error(hoja, fila, str(e))

        except Exception as e:
            logger.error("Fila %d: error inesperado — %s: %s", fila, type(e).__name__, e)
            _registrar_error(hoja, fila, f"{type(e).__name__}: {e}")

    logger.info(
        "%d/%d Reels publicados con éxito.",
        len(resultados),
        len(aprobados),
    )
    print(json.dumps(resultados, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
