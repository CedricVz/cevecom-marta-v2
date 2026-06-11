"""Sube un archivo local al OpenAI Vector Store del agente de DMs.

Uso:
    python tools/subir_openai_vector_file.py docs/knowledge/marta/botox_capilar.md

No borra archivos ni toca otros sistemas.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI

from config import cfg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sube un archivo local al OpenAI Vector Store.")
    parser.add_argument("path", help="Ruta del archivo local a subir.")
    return parser.parse_args()


def id_suffix(value: str) -> str:
    return value[-6:] if value else ""


def model_to_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    return {}


def main() -> None:
    args = parse_args()
    path = Path(args.path)
    if not path.exists() or not path.is_file():
        raise SystemExit(f"No existe el archivo local: {path}")

    client = OpenAI(api_key=cfg.openai_api_key)
    vector_store_id = cfg.openai_vector_store_id

    with path.open("rb") as f:
        vector_file = client.vector_stores.files.upload_and_poll(
            vector_store_id=vector_store_id,
            file=(path.name, f),
            poll_interval_ms=2000,
        )

    data = model_to_dict(vector_file)
    file_id = data.get("id") or data.get("file_id") or ""
    status = data.get("status", "")
    last_error = data.get("last_error") or data.get("error") or ""

    print(f"filename: {path.name}")
    print(f"file_id: {file_id}")
    print(f"vector_store_id: ...{id_suffix(vector_store_id)}")
    print(f"status: {status}")
    if last_error:
        print(f"error: {last_error}")

    if status != "completed":
        raise SystemExit(f"El archivo no terminó en completed: {status}")


if __name__ == "__main__":
    main()
