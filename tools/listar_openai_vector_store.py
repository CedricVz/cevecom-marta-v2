"""Lista archivos asociados al OpenAI Vector Store del agente de DMs.

Solo lectura: no sube, no borra y no descarga contenido de archivos.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI

from config import cfg

TERMINOS_INTERES = [
    "botox",
    "capilar",
    "frizz",
    "encrespado",
    "keratina",
    "alisado",
    "cabello",
    "tratamientos capilares",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lista archivos asociados al OPENAI_VECTOR_STORE_ID sin modificar nada."
    )
    parser.add_argument("--json", action="store_true", help="Muestra salida JSON además del resumen.")
    parser.add_argument("--limit", type=int, default=100, help="Tamaño de página para listar archivos.")
    return parser.parse_args()


def model_to_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    return {
        key: getattr(obj, key)
        for key in dir(obj)
        if not key.startswith("_") and not callable(getattr(obj, key, None))
    }


def safe_timestamp(value: Any) -> str:
    if value in {None, ""}:
        return ""
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return str(value)


def id_suffix(value: str) -> str:
    return value[-6:] if value else ""


def list_all_vector_files(client: OpenAI, vector_store_id: str, limit: int) -> list[Any]:
    page = client.vector_stores.files.list(vector_store_id=vector_store_id, limit=limit)
    items = list(page.data)
    while getattr(page, "has_next_page", lambda: False)():
        page = page.get_next_page()
        items.extend(page.data)
    return items


def retrieve_file_metadata(client: OpenAI, file_id: str) -> dict[str, Any]:
    try:
        return model_to_dict(client.files.retrieve(file_id))
    except Exception as exc:  # noqa: BLE001 - queremos registrar fallos de lectura
        return {"retrieve_error": f"{type(exc).__name__}: {exc}"}


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return " ".join(normalize_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(f"{k} {normalize_text(v)}" for k, v in value.items())
    return str(value).lower()


def main() -> None:
    args = parse_args()
    client = OpenAI(api_key=cfg.openai_api_key)
    vector_store_id = cfg.openai_vector_store_id

    rows = []
    for vector_file in list_all_vector_files(client, vector_store_id, args.limit):
        vector_data = model_to_dict(vector_file)
        file_id = vector_data.get("id") or vector_data.get("file_id") or ""
        file_data = retrieve_file_metadata(client, file_id) if file_id else {}
        filename = file_data.get("filename") or vector_data.get("filename") or ""
        search_blob = normalize_text(
            {
                "filename": filename,
                "vector_file": vector_data,
                "file": file_data,
            }
        )
        matched_terms = [term for term in TERMINOS_INTERES if term in search_blob]
        rows.append(
            {
                "file_id": file_id,
                "filename": filename,
                "status": vector_data.get("status", ""),
                "created_at": safe_timestamp(vector_data.get("created_at") or file_data.get("created_at")),
                "usage_bytes": vector_data.get("usage_bytes", ""),
                "file_bytes": file_data.get("bytes", ""),
                "purpose": file_data.get("purpose", ""),
                "matched_terms": matched_terms,
                "retrieve_error": file_data.get("retrieve_error", ""),
            }
        )

    relacionados = [row for row in rows if row["matched_terms"]]
    report = {
        "vector_store_id_suffix": id_suffix(vector_store_id),
        "total_files": len(rows),
        "files": rows,
        "related_files": relacionados,
        "content_retrieval_note": (
            "El SDK permite recuperar contenido con client.files.content(file_id), "
            "pero este script no lo ejecuta."
        ),
    }

    print(f"Vector Store: ...{id_suffix(vector_store_id)}")
    print(f"Archivos asociados: {len(rows)}")
    print()
    print("file_id\tfilename\tstatus\tcreated_at\tusage_bytes\tmatched_terms")
    for row in rows:
        print(
            "\t".join(
                [
                    row["file_id"],
                    row["filename"],
                    row["status"],
                    row["created_at"],
                    str(row["usage_bytes"]),
                    ", ".join(row["matched_terms"]),
                ]
            )
        )

    print()
    print("Relacionados con Botox/capilar/frizz/encrespado/keratina/alisado/cabello:")
    if relacionados:
        for row in relacionados:
            print(f"- {row['filename']} ({row['file_id']}): {', '.join(row['matched_terms'])}")
    else:
        print("- Ninguno por nombre/metadata segura.")

    print()
    print(report["content_retrieval_note"])
    if args.json:
        print()
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
