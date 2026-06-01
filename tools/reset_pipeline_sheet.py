"""Archiva y limpia Sheet1 del pipeline para empezar una tanda limpia.

Por defecto solo simula. Para ejecutar cambios reales:
  python tools/reset_pipeline_sheet.py --execute
"""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import gspread

from config import cfg
from tools._columnas import CABECERAS
from tools.google_creds import service_account_credentials

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger("reset_pipeline_sheet")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Archiva Sheet1 y limpia filas de datos preservando cabeceras."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Aplica los cambios reales. Sin esto solo muestra lo que haría.",
    )
    parser.add_argument(
        "--archive-prefix",
        default="Archivo_pipeline",
        help="Prefijo para la pestaña de archivo.",
    )
    return parser.parse_args()


def conectar() -> gspread.Spreadsheet:
    creds = service_account_credentials(SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(cfg.google_sheets_id)


def ensure_unique_title(spreadsheet: gspread.Spreadsheet, base: str) -> str:
    existing = {worksheet.title for worksheet in spreadsheet.worksheets()}
    if base not in existing:
        return base
    suffix = 2
    while f"{base}_{suffix}" in existing:
        suffix += 1
    return f"{base}_{suffix}"


def main() -> None:
    args = parse_args()
    spreadsheet = conectar()
    sheet = spreadsheet.sheet1
    values = sheet.get_all_values()

    if not values:
        logger.info("Sheet1 está vacía. Se restaurarían cabeceras.")
        data_rows = 0
    else:
        data_rows = max(0, len(values) - 1)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    archive_title = ensure_unique_title(spreadsheet, f"{args.archive_prefix}_{timestamp}")

    logger.info("Documento: %s", spreadsheet.title)
    logger.info("Sheet1 tiene %d fila(s) de datos para archivar/limpiar.", data_rows)
    logger.info("Pestaña de archivo propuesta: %s", archive_title)

    if not args.execute:
        logger.info("DRY-RUN: no se escribió nada. Usa --execute para aplicar.")
        return

    if values:
        archive = spreadsheet.add_worksheet(
            title=archive_title,
            rows=max(len(values), 1),
            cols=max(len(values[0]), len(CABECERAS)),
        )
        archive.update("A1", values, value_input_option="RAW")
        logger.info("Archivo creado: %s", archive_title)

    sheet.clear()
    sheet.update("A1", [CABECERAS], value_input_option="RAW")
    logger.info("Sheet1 limpiada y cabeceras restauradas.")


if __name__ == "__main__":
    main()
