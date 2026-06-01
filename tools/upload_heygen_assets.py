"""Sube B-roll del catálogo a HeyGen Assets y devuelve asset_id.

Por defecto solo simula. Para subir realmente:
  python tools/upload_heygen_assets.py --execute

También permite filtrar:
  python tools/upload_heygen_assets.py --execute --labels "clienta entrando al salón" "laser"
"""

import argparse
import io
import json
import logging
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from google.auth.transport.requests import Request

from config import cfg
from tools.generar_video import ASSET_CATALOG
from tools.google_creds import service_account_credentials

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger("upload_heygen_assets")

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
MAX_ASSET_BYTES = 32 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sube assets de Drive a HeyGen Assets.")
    parser.add_argument("--execute", action="store_true", help="Sube realmente los assets.")
    parser.add_argument("--labels", nargs="*", help="Sube solo assets con estos labels exactos.")
    parser.add_argument(
        "--local",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="Sube un archivo local para el label indicado. Puede repetirse.",
    )
    return parser.parse_args()


def drive_file_id(url: str) -> str:
    match = re.search(r"/file/d/([^/]+)/", url)
    if match:
        return match.group(1)
    parsed = urlparse(url)
    return parse_qs(parsed.query).get("id", [""])[0]


def public_download_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def drive_headers() -> dict[str, str]:
    creds = service_account_credentials(SCOPES)
    creds.refresh(Request())
    return {"Authorization": f"Bearer {creds.token}"}


def get_drive_metadata(file_id: str, headers: dict[str, str]) -> dict:
    r = requests.get(
        f"https://www.googleapis.com/drive/v3/files/{file_id}",
        params={"fields": "id,name,mimeType,size"},
        headers=headers,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def download_drive_file(file_id: str, headers: dict[str, str]) -> bytes:
    r = requests.get(
        f"https://www.googleapis.com/drive/v3/files/{file_id}",
        params={"alt": "media"},
        headers=headers,
        timeout=120,
    )
    r.raise_for_status()
    return r.content


def get_public_metadata(file_id: str) -> dict:
    r = requests.get(public_download_url(file_id), stream=True, allow_redirects=True, timeout=30)
    content_type = r.headers.get("Content-Type", "application/octet-stream")
    size = int(r.headers.get("Content-Length") or 0)
    first_chunk = next(r.iter_content(16), b"")
    r.close()
    if first_chunk.startswith(b"<!DOCTYPE") or first_chunk.startswith(b"<html"):
        raise RuntimeError("Drive devolvió HTML en vez de vídeo")
    return {
        "id": file_id,
        "name": f"{file_id}.mp4",
        "mimeType": content_type,
        "size": str(size),
        "source": "public",
    }


def download_public_file(file_id: str) -> bytes:
    r = requests.get(public_download_url(file_id), timeout=120)
    r.raise_for_status()
    if r.content.startswith(b"<!DOCTYPE") or r.content.startswith(b"<html"):
        raise RuntimeError("Drive devolvió HTML en vez de vídeo")
    return r.content


def upload_to_heygen(filename: str, content: bytes, mime_type: str) -> dict:
    r = requests.post(
        "https://api.heygen.com/v3/assets",
        headers={
            "x-api-key": cfg.heygen_api_key,
            "Idempotency-Key": f"marta_asset_{uuid.uuid4().hex}",
        },
        files={"file": (filename, io.BytesIO(content), mime_type)},
        timeout=180,
    )
    r.raise_for_status()
    return r.json()["data"]


def guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".mp4":
        return "video/mp4"
    if suffix in {".mov", ".qt"}:
        return "video/quicktime"
    return "application/octet-stream"


def parse_local_assets(entries: list[str]) -> dict[str, Path]:
    parsed = {}
    for entry in entries:
        if "=" not in entry:
            raise SystemExit(f"--local debe tener formato LABEL=PATH: {entry}")
        label, raw_path = entry.split("=", 1)
        path = Path(raw_path.strip().strip('"'))
        if not path.exists():
            raise SystemExit(f"No existe archivo local para {label}: {path}")
        parsed[label.strip()] = path
    return parsed


def main() -> None:
    args = parse_args()
    selected_labels = set(args.labels or [])
    local_assets = parse_local_assets(args.local)
    headers = drive_headers()
    output = []

    for asset in ASSET_CATALOG:
        label = asset["label"]
        if selected_labels and label not in selected_labels:
            continue
        if asset.get("asset_id"):
            logger.info("%s: ya tiene asset_id=%s", label, asset["asset_id"])
            output.append({"label": label, "asset_id": asset["asset_id"], "status": "exists"})
            continue

        if label in local_assets:
            path = local_assets[label]
            size = path.stat().st_size
            mime_type = guess_mime_type(path)
            if size > MAX_ASSET_BYTES:
                logger.warning("%s: omitido, %.1f MB supera límite 32 MB", label, size / 1024 / 1024)
                output.append({"label": label, "status": "too_large", "size_bytes": size})
                continue
            if not args.execute:
                logger.info("%s: DRY-RUN subiría local %.1f MB (%s)", label, size / 1024 / 1024, mime_type)
                output.append({"label": label, "status": "dry_run_local", "size_bytes": size})
                continue
            logger.info("%s: subiendo archivo local %.1f MB", label, size / 1024 / 1024)
            data = upload_to_heygen(path.name, path.read_bytes(), mime_type)
            output.append({"label": label, "status": "uploaded", **data})
            logger.info("%s: asset_id=%s", label, data["asset_id"])
            continue

        file_id = drive_file_id(asset["url"])
        try:
            metadata = get_drive_metadata(file_id, headers)
            source = "drive_api"
        except requests.HTTPError as e:
            logger.warning("%s: Drive API no accesible (%s), probando URL pública", label, e.response.status_code)
            try:
                metadata = get_public_metadata(file_id)
                source = "public"
            except Exception as public_error:
                logger.warning("%s: omitido, no se pudo leer vídeo público: %s", label, public_error)
                output.append({"label": label, "status": "not_accessible"})
                continue
        size = int(metadata.get("size") or 0)
        mime_type = metadata.get("mimeType") or "application/octet-stream"
        filename = metadata.get("name") or f"{label}.mp4"

        if size > MAX_ASSET_BYTES:
            logger.warning("%s: omitido, %.1f MB supera límite 32 MB", label, size / 1024 / 1024)
            output.append({"label": label, "status": "too_large", "size_bytes": size})
            continue

        if not args.execute:
            logger.info("%s: DRY-RUN subiría %.1f MB (%s, %s)", label, size / 1024 / 1024, mime_type, source)
            output.append({"label": label, "status": "dry_run", "size_bytes": size})
            continue

        logger.info("%s: descargando %.1f MB y subiendo a HeyGen", label, size / 1024 / 1024)
        content = (
            download_drive_file(file_id, headers)
            if source == "drive_api"
            else download_public_file(file_id)
        )
        data = upload_to_heygen(filename, content, mime_type)
        output.append({"label": label, "status": "uploaded", **data})
        logger.info("%s: asset_id=%s", label, data["asset_id"])

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
