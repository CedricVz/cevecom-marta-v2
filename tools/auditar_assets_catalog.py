"""Audita ASSET_CATALOG contra Drive y HeyGen sin modificar nada.

La salida se guarda en videos_generados/asset_audit/asset_audit.json.
No llama a render, no sube archivos y no toca Sheets.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.generar_video import ASSET_CATALOG

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "videos_generados" / "asset_audit"
DRIVE_DIR = OUT_DIR / "drive_originales"

LAST_RENDER_LABELS = {
    "clienta entrando al salón",
    "entrada del salón",
    "maderoterapia en camilla",
    "HIFU brazos",
    "clienta cancelando cita",
    "silla vacía del salón",
    "aplicar crema facial",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audita metadata técnica de ASSET_CATALOG.")
    parser.add_argument(
        "--skip-drive-download",
        action="store_true",
        help="No descarga Drive; usa solo HeyGen original URL cuando haya asset_id.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Vuelve a descargar archivos de Drive aunque exista caché.",
    )
    return parser.parse_args()


def slugify(text: str) -> str:
    replacements = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    clean = text.translate(replacements)
    clean = re.sub(r"[^A-Za-z0-9]+", "_", clean).strip("_").lower()
    return clean or "asset"


def drive_file_id(url: str) -> str:
    match = re.search(r"/file/d/([^/]+)/", url or "")
    if match:
        return match.group(1)
    parsed = urlparse(url or "")
    return parse_qs(parsed.query).get("id", [""])[0]


def public_drive_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def heygen_original_url(asset_id: str) -> str:
    return f"https://resource2.heygen.ai/video/{asset_id}/original.mp4"


def extract_drive_confirm_token(html: str) -> str:
    for pattern in (r"confirm=([0-9A-Za-z_]+)", r'name="confirm"\s+value="([^"]+)"'):
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return ""


def filename_from_content_disposition(value: str) -> str:
    if not value:
        return ""
    message = Message()
    message["content-disposition"] = value
    filename = message.get_filename()
    return unquote(filename or "")


def download_drive(asset: dict[str, Any], force: bool) -> dict[str, Any]:
    url = asset.get("url", "")
    file_id = drive_file_id(url)
    if not file_id:
        return {"status": "sin_drive_url", "file_id": "", "path": "", "filename": "", "error": ""}

    path = DRIVE_DIR / f"{slugify(asset['label'])}_{file_id}.mp4"
    if path.exists() and not force:
        return {
            "status": "cache",
            "file_id": file_id,
            "path": str(path),
            "filename": path.name,
            "bytes": path.stat().st_size,
            "error": "",
        }

    DRIVE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with requests.Session() as session:
            response = session.get(public_drive_url(file_id), stream=True, allow_redirects=True, timeout=60)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            content_disposition = response.headers.get("Content-Disposition", "")
            first_chunk = next(response.iter_content(8192), b"")

            if b"<html" in first_chunk[:512].lower() or "text/html" in content_type.lower():
                token = extract_drive_confirm_token(first_chunk.decode("utf-8", errors="ignore"))
                response.close()
                if not token:
                    raise RuntimeError("Drive devolvió HTML sin token de confirmación")
                response = session.get(
                    public_drive_url(file_id) + f"&confirm={token}",
                    stream=True,
                    allow_redirects=True,
                    timeout=60,
                )
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "")
                content_disposition = response.headers.get("Content-Disposition", "")
                first_chunk = next(response.iter_content(8192), b"")
                if b"<html" in first_chunk[:512].lower() or "text/html" in content_type.lower():
                    raise RuntimeError("Drive siguió devolviendo HTML tras confirmación")

            filename = filename_from_content_disposition(content_disposition) or path.name
            total = 0
            with path.open("wb") as f:
                if first_chunk:
                    f.write(first_chunk)
                    total += len(first_chunk)
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
            response.close()
            return {
                "status": "descargado",
                "file_id": file_id,
                "path": str(path),
                "filename": filename,
                "bytes": total,
                "content_type": content_type,
                "error": "",
            }
    except Exception as exc:  # noqa: BLE001 - diagnóstico explícito
        return {"status": "error", "file_id": file_id, "path": "", "filename": "", "error": str(exc)}


def find_binary(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    known = (
        Path.home()
        / "AppData"
        / "Local"
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
        / "ffmpeg-8.1.1-full_build"
        / "bin"
        / f"{name}.exe"
    )
    if known.exists():
        return str(known)
    raise SystemExit(f"No encuentro {name}.")


def ffprobe(target: str, ffprobe_bin: str) -> tuple[dict[str, Any] | None, str]:
    try:
        proc = subprocess.run(
            [
                ffprobe_bin,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                target,
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90,
        )
        return json.loads(proc.stdout), ""
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def video_stream(metadata: dict[str, Any]) -> dict[str, Any]:
    for stream in metadata.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    return {}


def stream_rotation(stream: dict[str, Any]) -> int:
    rotate = stream.get("tags", {}).get("rotate")
    if rotate:
        try:
            return int(float(rotate))
        except ValueError:
            return 0
    for side_data in stream.get("side_data_list", []):
        if "rotation" in side_data:
            try:
                return int(float(side_data["rotation"]))
            except ValueError:
                return 0
    return 0


def summarize(metadata: dict[str, Any] | None, target: str) -> dict[str, Any]:
    if not metadata:
        return {}
    stream = video_stream(metadata)
    fmt = metadata.get("format", {})
    duration = stream.get("duration") or fmt.get("duration") or ""
    return {
        "target": target,
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "sar": stream.get("sample_aspect_ratio", ""),
        "dar": stream.get("display_aspect_ratio", ""),
        "rotation": stream_rotation(stream),
        "duration": float(duration) if duration not in {"", None} else None,
        "codec": stream.get("codec_name", ""),
        "format_name": fmt.get("format_name", ""),
        "size_bytes": int(fmt.get("size") or 0),
    }


def ratio(raw: str) -> float | None:
    if not raw or ":" not in raw or raw == "0:1":
        return None
    left, right = raw.split(":", 1)
    try:
        denominator = float(right)
        return None if denominator == 0 else float(left) / denominator
    except ValueError:
        return None


def classify(meta: dict[str, Any]) -> str:
    if not meta:
        return "desconocido"
    width = int(meta.get("width") or 0)
    height = int(meta.get("height") or 0)
    rotation = abs(int(meta.get("rotation") or 0))
    sar = meta.get("sar") or ""
    dar_value = ratio(meta.get("dar") or "")
    portrait_dar = dar_value is not None and 0.48 <= dar_value <= 0.64
    sar_safe = sar in {"", "1:1"}

    if width < height and rotation == 0 and sar_safe:
        return "portrait_real_seguro"
    if rotation in {90, 270} or portrait_dar or (width == height and not sar_safe):
        return "portrait_por_metadata"
    if width > height:
        return "landscape_real"
    return "desconocido"


def differs(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if not a or not b:
        return False
    keys = ["width", "height", "sar", "dar", "rotation", "duration", "codec"]
    for key in keys:
        if key == "duration":
            av = a.get(key)
            bv = b.get(key)
            if av is not None and bv is not None and abs(float(av) - float(bv)) > 0.2:
                return True
        elif a.get(key) != b.get(key):
            return True
    return False


def main() -> None:
    args = parse_args()
    ffprobe_bin = find_binary("ffprobe")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for asset in ASSET_CATALOG:
        print(f"[audit] {asset['label']}", file=sys.stderr)
        drive = (
            {"status": "omitido", "file_id": drive_file_id(asset.get("url", "")), "path": "", "filename": "", "error": ""}
            if args.skip_drive_download
            else download_drive(asset, args.force_download)
        )

        drive_meta = {}
        drive_probe_error = ""
        if drive.get("path"):
            raw, drive_probe_error = ffprobe(drive["path"], ffprobe_bin)
            drive_meta = summarize(raw, drive["path"]) if raw else {}

        heygen_meta = {}
        heygen_probe_error = ""
        heygen_url = heygen_original_url(asset.get("asset_id", "")) if asset.get("asset_id") else ""
        if heygen_url:
            raw, heygen_probe_error = ffprobe(heygen_url, ffprobe_bin)
            heygen_meta = summarize(raw, heygen_url) if raw else {}

        preferred = drive_meta or heygen_meta
        category = classify(preferred)
        rows.append(
            {
                "label": asset.get("label", ""),
                "drive_filename": drive.get("filename", ""),
                "drive_url": asset.get("url", ""),
                "drive_file_id": drive.get("file_id", ""),
                "asset_id": asset.get("asset_id", ""),
                "keywords": asset.get("keywords", []),
                "used_in_last_renders": asset.get("label", "") in LAST_RENDER_LABELS,
                "visualmente_deberia_ser_reel": True,
                "drive_download": drive,
                "drive_metadata": drive_meta,
                "drive_probe_error": drive_probe_error,
                "heygen_original_url": heygen_url,
                "heygen_metadata": heygen_meta,
                "heygen_probe_error": heygen_probe_error,
                "classification": category,
                "drive_vs_heygen_differ": differs(drive_meta, heygen_meta),
                "possible_old_heygen_asset": differs(drive_meta, heygen_meta),
            }
        )

    by_category: dict[str, list[str]] = {}
    for row in rows:
        by_category.setdefault(row["classification"], []).append(row["label"])

    report = {
        "notes": [
            "Auditoría diagnóstica local. No render, no subida, no Sheets.",
            "classification usa metadata de Drive si existe; si no, usa HeyGen original.",
            "possible_old_heygen_asset=True cuando Drive y HeyGen original difieren técnicamente.",
        ],
        "rows": rows,
        "by_category": by_category,
    }
    out = OUT_DIR / "asset_audit.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
