"""Lee una fila existente de Sheet1 y la emite como JSON para reintentos.

Uso:
  python tools/leer_pipeline_row.py --row 5 | python tools/generar_video.py
"""

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import gspread

from config import cfg
from tools._columnas import CABECERAS
from tools.google_creds import service_account_credentials

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger("leer_pipeline_row")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lee una fila existente de Sheet1 para reintentar generación sin duplicar."
    )
    parser.add_argument(
        "--row",
        type=int,
        required=True,
        help="Número real de fila en Sheet1/Pipeline.",
    )
    args = parser.parse_args()
    if args.row < 2:
        parser.error("--row debe ser 2 o mayor (fila 1=cabeceras)")
    return args


def conectar() -> gspread.Worksheet:
    creds = service_account_credentials(SCOPES)
    gc = gspread.authorize(creds)
    return gc.open_by_key(cfg.google_sheets_id).sheet1


def get_cell(row: list[str], index: int) -> str:
    return row[index].strip() if index < len(row) else ""


def main() -> None:
    args = parse_args()
    ws = conectar()
    row_values = ws.row_values(args.row)
    item = {
        "fila": args.row,
        **{
            header.lower(): get_cell(row_values, index)
            for index, header in enumerate(CABECERAS)
        },
    }

    if not item.get("tema") or not item.get("guion"):
        logger.error("Fila %d sin Tema o Guion; no se puede reintentar.", args.row)
        sys.exit(1)

    logger.info("Fila %d (Pipeline) -> reintentando: %s", args.row, item["tema"])
    print(json.dumps([item], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
