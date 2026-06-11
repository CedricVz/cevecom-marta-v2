"""Descarga localmente un archivo de OpenAI por file_id para auditoría.

Solo lectura: no sube, no borra y no modifica el Vector Store.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from openai import OpenAI

from config import cfg

OUT_DIR = Path(__file__).resolve().parent.parent / "videos_generados" / "vector_store_audit"
QUERIES_AUDITORIA = [
    "botox capilar frizz encrespado alisado resultado permanente garantizado",
    "elimina el frizz elimina el encrespado elimina por completo alisado definitivo",
    "suavidad hidratación brillo duración botox capilar keratina cabello",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Descarga un archivo OpenAI por file_id.")
    parser.add_argument("file_id", help="ID del archivo, por ejemplo file-...")
    return parser.parse_args()


def model_to_dict(obj: Any) -> dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    return {}


def safe_filename(name: str, fallback: str) -> str:
    clean = name.strip() or fallback
    clean = re.sub(r'[<>:"/\\\\|?*]+', "_", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean or fallback


def read_content_bytes(content: Any) -> bytes:
    if hasattr(content, "read"):
        data = content.read()
        return data if isinstance(data, bytes) else str(data).encode("utf-8")
    if hasattr(content, "content"):
        data = content.content
        return data if isinstance(data, bytes) else str(data).encode("utf-8")
    if isinstance(content, bytes):
        return content
    if isinstance(content, str):
        return content.encode("utf-8")
    raise TypeError(f"No sé convertir contenido de tipo {type(content).__name__} a bytes")


def search_file_snippets(client: OpenAI, file_id: str) -> list[dict[str, Any]]:
    snippets: list[dict[str, Any]] = []
    seen: set[str] = set()
    for query in QUERIES_AUDITORIA:
        page = client.vector_stores.search(
            vector_store_id=cfg.openai_vector_store_id,
            query=query,
            max_num_results=10,
        )
        for result in page.data:
            data = model_to_dict(result)
            if data.get("file_id") != file_id:
                continue
            text_parts = [
                part.get("text", "")
                for part in data.get("content", [])
                if isinstance(part, dict) and part.get("text")
            ]
            text = "\n".join(text_parts).strip()
            key = text[:500]
            if not text or key in seen:
                continue
            seen.add(key)
            snippets.append(
                {
                    "query": query,
                    "file_id": data.get("file_id", ""),
                    "filename": data.get("filename", ""),
                    "score": data.get("score", ""),
                    "text": text,
                }
            )
    return snippets


def save_snippets(file_id: str, filename: str, snippets: list[dict[str, Any]], error: str) -> Path:
    base = safe_filename(filename, file_id)
    json_path = OUT_DIR / f"{file_id}_{base}.snippets.json"
    txt_path = OUT_DIR / f"{file_id}_{base}.snippets.txt"
    payload = {
        "file_id": file_id,
        "filename": filename,
        "download_error": error,
        "note": "Snippets recuperados con vector_stores.search; no es el contenido completo del archivo.",
        "snippets": snippets,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_lines = [
        f"file_id: {file_id}",
        f"filename: {filename}",
        f"download_error: {error}",
        "note: Snippets recuperados con vector_stores.search; no es el contenido completo del archivo.",
        "",
    ]
    for index, snippet in enumerate(snippets, 1):
        txt_lines.extend(
            [
                f"--- snippet {index}",
                f"query: {snippet['query']}",
                f"score: {snippet['score']}",
                snippet["text"],
                "",
            ]
        )
    txt_path.write_text("\n".join(txt_lines), encoding="utf-8")
    return txt_path


def main() -> None:
    args = parse_args()
    client = OpenAI(api_key=cfg.openai_api_key)

    metadata = model_to_dict(client.files.retrieve(args.file_id))
    filename = safe_filename(metadata.get("filename", ""), f"{args.file_id}.bin")
    output_path = OUT_DIR / f"{args.file_id}_{filename}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        content = client.files.content(args.file_id)
        output_path.write_bytes(read_content_bytes(content))
        print(f"file_id: {args.file_id}")
        print(f"filename: {filename}")
        print(f"purpose: {metadata.get('purpose', '')}")
        print(f"bytes: {output_path.stat().st_size}")
        print(f"local_path: {output_path}")
        return
    except Exception as exc:  # noqa: BLE001 - si OpenAI bloquea descarga, hacemos fallback read-only
        error = f"{type(exc).__name__}: {exc}"
        snippets = search_file_snippets(client, args.file_id)
        snippets_path = save_snippets(args.file_id, filename, snippets, error)

    print(f"file_id: {args.file_id}")
    print(f"filename: {filename}")
    print(f"purpose: {metadata.get('purpose', '')}")
    print(f"download_blocked: true")
    print(f"download_error: {error}")
    print(f"snippets_count: {len(snippets)}")
    print(f"snippets_path: {snippets_path}")


if __name__ == "__main__":
    main()
