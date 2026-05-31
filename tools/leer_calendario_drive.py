"""
tools/leer_calendario_drive.py — Lee guiones escritos por Marta e inyecta en el pipeline (v3).

Lee la pestaña "Guiones_Marta" del spreadsheet, busca filas con Guion relleno
y Estado_proceso vacío, las copia al Pipeline (Sheet1) con Estado="Generando vídeo"
y vuelca JSON a stdout para que generar_video.py lo procese.

Pipeline v3 (sin generar_guion.py):
  leer_calendario_drive.py → generar_video.py → enviar_aprobacion.py

Prerrequisito: la pestaña "Guiones_Marta" debe existir en CALENDARIO_MARTA_SHEETS_ID.

Uso:
  python tools/leer_calendario_drive.py
  python tools/leer_calendario_drive.py --limit 3
  python tools/leer_calendario_drive.py --marta-row 8 --dry-run
  cmd /c "python tools\\leer_calendario_drive.py | python tools\\generar_video.py | python tools\\enviar_aprobacion.py"
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import gspread

from config import cfg
from tools._columnas import CABECERAS, COL
from tools.google_creds import service_account_credentials

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger("leer_calendario_drive")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

TAB_MARTA = "Guiones_Marta"

# Columnas del spreadsheet de Marta (base 1, mismo orden que sus cabeceras)
MARTA_COL = {
    "Tema": 1,
    "Tratamiento": 2,
    "Audiencia": 3,
    "Tono": 4,
    "Look_ID": 5,
    "Fecha_deseada": 6,
    "Guion": 7,
    "Notas_escenas": 8,   # dirección de escena para el Video Agent (lo lee generar_video.py)
    "Estado_proceso": 9,  # el sistema escribe aquí tras procesar la fila
}


def get_cell(row: list, col: int) -> str:
    idx = col - 1
    return row[idx].strip() if idx < len(row) else ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lee Guiones_Marta e inyecta filas seleccionadas en Sheet1."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Máximo de filas de Marta a procesar (ej: 3 para el cron semanal).",
    )
    parser.add_argument(
        "--marta-row",
        type=int,
        default=None,
        help="Procesa solo una fila concreta de Guiones_Marta (número real de fila).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra el JSON que se procesaría sin escribir en ninguna hoja.",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit debe ser mayor o igual que 1")
    if args.marta_row is not None and args.marta_row < 3:
        parser.error("--marta-row debe ser 3 o mayor (fila 1=cabeceras, fila 2=instrucciones)")
    return args


def conectar() -> tuple[gspread.Worksheet, gspread.Worksheet]:
    if not cfg.calendario_marta_sheets_id:
        logger.error(
            "CALENDARIO_MARTA_SHEETS_ID no está configurado en el .env. "
            "Añade la variable con el ID del spreadsheet de Marta."
        )
        sys.exit(1)

    creds = service_account_credentials(SCOPES)
    gc = gspread.authorize(creds)

    # Spreadsheet de Marta — pestaña donde ella escribe sus guiones
    sh_marta = gc.open_by_key(cfg.calendario_marta_sheets_id)
    try:
        ws_marta = sh_marta.worksheet(TAB_MARTA)
    except gspread.WorksheetNotFound:
        logger.error(
            "No existe la pestaña '%s' en el spreadsheet de Marta. "
            "Créala manualmente en Google Sheets con las columnas del sistema.",
            TAB_MARTA,
        )
        sys.exit(1)

    # Spreadsheet del pipeline — donde el sistema gestiona el proceso completo
    sh_pipeline = gc.open_by_key(cfg.google_sheets_id)

    return ws_marta, sh_pipeline.sheet1


def main() -> None:
    args = parse_args()

    try:
        ws_marta, ws_pipeline = conectar()
    except gspread.exceptions.SpreadsheetNotFound as e:
        logger.error(
            "No se encontró una de las hojas (%s). "
            "Verifica que la service account tenga acceso a CALENDARIO_MARTA_SHEETS_ID "
            "y a GOOGLE_SHEETS_ID.",
            e,
        )
        sys.exit(1)
    except FileNotFoundError:
        logger.error("No se encontró credentials.json en %s", cfg.google_credentials_path)
        sys.exit(1)

    todas = ws_marta.get_all_values()
    if len(todas) <= 1:
        logger.info("No hay filas de datos en el spreadsheet de Marta.")
        print("[]")
        return

    output = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    pipeline_row_count = len(ws_pipeline.get_all_values())
    seleccionadas = 0

    # Fila 1 = cabeceras, fila 2 = instrucciones — datos desde fila 3
    for i, marta_row in enumerate(todas[2:], start=3):
        if args.marta_row is not None and i != args.marta_row:
            continue

        tema = get_cell(marta_row, MARTA_COL["Tema"])
        guion = get_cell(marta_row, MARTA_COL["Guion"])
        notas_escenas = get_cell(marta_row, MARTA_COL["Notas_escenas"])
        estado_proceso = get_cell(marta_row, MARTA_COL["Estado_proceso"])

        if not tema or not guion:
            continue
        if estado_proceso:
            continue  # ya procesada en ejecuciones anteriores

        if args.limit is not None and seleccionadas >= args.limit:
            continue

        accion = "simulando" if args.dry_run else "inyectando en pipeline"
        logger.info("Fila %d (Marta) → %s: %s", i, accion, tema)

        # Construye la fila completa del Pipeline (mismo orden que CABECERAS / Sheet1)
        pipeline_row = [""] * len(CABECERAS)
        pipeline_row[COL["Tema"] - 1]          = tema
        pipeline_row[COL["Tratamiento"] - 1]   = get_cell(marta_row, MARTA_COL["Tratamiento"])
        pipeline_row[COL["Audiencia"] - 1]     = get_cell(marta_row, MARTA_COL["Audiencia"])
        pipeline_row[COL["Tono"] - 1]          = get_cell(marta_row, MARTA_COL["Tono"])
        pipeline_row[COL["Look_ID"] - 1]       = get_cell(marta_row, MARTA_COL["Look_ID"])
        pipeline_row[COL["Fecha_deseada"] - 1] = get_cell(marta_row, MARTA_COL["Fecha_deseada"])
        pipeline_row[COL["Estado"] - 1]        = "Generando vídeo"
        pipeline_row[COL["Guion"] - 1]         = guion
        pipeline_row[COL["Notas_escenas"] - 1] = notas_escenas

        # Calcula el número de fila ANTES de añadir (get_all_values incluye cabecera)
        nueva_fila = pipeline_row_count + seleccionadas + 1

        if not args.dry_run:
            ws_pipeline.append_row(pipeline_row, value_input_option="RAW")
            ws_marta.update_cell(i, MARTA_COL["Estado_proceso"], f"Procesado ✓ {ts}")

        output.append({
            "fila": nueva_fila,
            "marta_fila": i,
            "tema": tema,
            "tratamiento": get_cell(marta_row, MARTA_COL["Tratamiento"]),
            "audiencia": get_cell(marta_row, MARTA_COL["Audiencia"]),
            "tono": get_cell(marta_row, MARTA_COL["Tono"]),
            "look_id": get_cell(marta_row, MARTA_COL["Look_ID"]),
            "fecha_deseada": get_cell(marta_row, MARTA_COL["Fecha_deseada"]),
            "guion": guion,
            "notas_escenas": notas_escenas,
        })
        seleccionadas += 1

    if args.dry_run:
        logger.info("%d fila(s) seleccionadas en dry-run. No se escribió en Sheets.", len(output))
    else:
        logger.info("%d fila(s) inyectadas en el pipeline.", len(output))
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
