"""Normaliza B-roll problemático a MP4 vertical real 1080x1920.

Este script es una prueba local: descarga originales, genera versiones 9:16
normalizadas y crea previews/contact sheet. No sube nada a HeyGen ni modifica
el catálogo.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.generar_video import ASSET_CATALOG

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "videos_generados" / "assets_normalizados"
ORIGINALS_DIR = OUTPUT_DIR / "originales"
PREVIEWS_DIR = OUTPUT_DIR / "previews"
CONTACT_SHEET = OUTPUT_DIR / "contact_sheet.jpg"

TARGET_LABELS = [
    "entrada del salón",
    "maderoterapia en camilla",
    "HIFU brazos",
    "clienta cancelando cita",
    "silla vacía del salón",
    "aplicar crema facial",
]


@dataclass(frozen=True)
class Target:
    label: str
    url: str
    asset_id: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normaliza assets de Marta a vertical 9:16.")
    parser.add_argument(
        "--strategy",
        choices=["auto", "crop", "blur"],
        default="auto",
        help="Estrategia visual para el MP4 primario.",
    )
    parser.add_argument(
        "--also-blur-fallback",
        action="store_true",
        help="Además del primario, crea una variante blur para revisión visual.",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Vuelve a descargar aunque el original exista localmente.",
    )
    return parser.parse_args()


def slugify(text: str) -> str:
    replacements = {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "ñ": "n",
        "Á": "A",
        "É": "E",
        "Í": "I",
        "Ó": "O",
        "Ú": "U",
        "Ü": "U",
        "Ñ": "N",
    }
    clean = "".join(replacements.get(ch, ch) for ch in text)
    clean = re.sub(r"[^A-Za-z0-9]+", "_", clean).strip("_").lower()
    return clean or "asset"


def catalog_targets() -> list[Target]:
    by_label = {asset["label"]: asset for asset in ASSET_CATALOG}
    missing = [label for label in TARGET_LABELS if label not in by_label]
    if missing:
        raise SystemExit(f"No están en ASSET_CATALOG: {', '.join(missing)}")
    return [
        Target(label=label, url=by_label[label].get("url", ""), asset_id=by_label[label].get("asset_id", ""))
        for label in TARGET_LABELS
    ]


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


def download_stream(url: str, path: Path) -> tuple[str, int]:
    with requests.Session() as session:
        response = session.get(url, stream=True, allow_redirects=True, timeout=60)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        content_disposition = response.headers.get("Content-Disposition", "")
        first_chunk = next(response.iter_content(8192), b"")

        if b"<html" in first_chunk[:512].lower() or "text/html" in content_type.lower():
            token = extract_drive_confirm_token(first_chunk.decode("utf-8", errors="ignore"))
            response.close()
            if not token:
                raise RuntimeError("la URL devolvió HTML, no bytes de vídeo")
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            file_id = query.get("id", [""])[0]
            retry = session.get(
                public_drive_url(file_id) + f"&confirm={token}",
                stream=True,
                allow_redirects=True,
                timeout=60,
            )
            retry.raise_for_status()
            response = retry
            content_type = response.headers.get("Content-Type", "")
            content_disposition = response.headers.get("Content-Disposition", "")
            first_chunk = next(response.iter_content(8192), b"")
            if b"<html" in first_chunk[:512].lower() or "text/html" in content_type.lower():
                response.close()
                raise RuntimeError("Drive siguió devolviendo HTML tras confirmación")

        path.parent.mkdir(parents=True, exist_ok=True)
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
        source_hint = "drive_public" if "drive.google.com" in url else "heygen_original"
        if content_disposition:
            source_hint += "_attachment"
        return source_hint, total


def extract_drive_confirm_token(html: str) -> str:
    patterns = [
        r'confirm=([0-9A-Za-z_]+)',
        r'name="confirm"\s+value="([^"]+)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return match.group(1)
    return ""


def download_original(target: Target, force: bool) -> dict[str, Any]:
    local_path = ORIGINALS_DIR / f"{slugify(target.label)}_{target.asset_id}.mp4"
    if local_path.exists() and not force:
        return {
            "path": str(local_path),
            "downloaded": False,
            "source_used": "local_cache",
            "bytes": local_path.stat().st_size,
            "drive_attempted": bool(target.url),
            "drive_error": "",
        }

    drive_error = ""
    if target.url:
        file_id = drive_file_id(target.url)
        if file_id:
            try:
                source_used, size = download_stream(public_drive_url(file_id), local_path)
                return {
                    "path": str(local_path),
                    "downloaded": True,
                    "source_used": source_used,
                    "bytes": size,
                    "drive_attempted": True,
                    "drive_error": "",
                }
            except Exception as exc:  # noqa: BLE001 - queremos registrar el motivo exacto
                drive_error = str(exc)

    source_used, size = download_stream(heygen_original_url(target.asset_id), local_path)
    return {
        "path": str(local_path),
        "downloaded": True,
        "source_used": source_used,
        "bytes": size,
        "drive_attempted": bool(target.url),
        "drive_error": drive_error,
    }


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
    raise SystemExit(f"No encuentro {name}. Añádelo al PATH o instala FFmpeg.")


def run_json(command: list[str]) -> dict[str, Any]:
    proc = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(proc.stdout)


def run_command(command: list[str]) -> str:
    proc = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
    return (proc.stdout + proc.stderr).strip()


def ffprobe(path: Path, ffprobe_bin: str) -> dict[str, Any]:
    return run_json(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-show_format",
            str(path),
        ]
    )


def video_stream(metadata: dict[str, Any]) -> dict[str, Any]:
    for stream in metadata.get("streams", []):
        if stream.get("codec_type") == "video":
            return stream
    raise RuntimeError("No hay stream de vídeo")


def stream_rotation(stream: dict[str, Any]) -> int:
    rotate = stream.get("tags", {}).get("rotate")
    if rotate:
        try:
            return int(float(rotate))
        except ValueError:
            pass
    for side_data in stream.get("side_data_list", []):
        if "rotation" in side_data:
            try:
                return int(float(side_data["rotation"]))
            except ValueError:
                return 0
    return 0


def ratio_value(raw: str) -> float | None:
    if not raw or raw == "0:1":
        return None
    if ":" not in raw:
        return None
    left, right = raw.split(":", 1)
    try:
        denominator = float(right)
        if denominator == 0:
            return None
        return float(left) / denominator
    except ValueError:
        return None


def metadata_summary(path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    stream = video_stream(metadata)
    fmt = metadata.get("format", {})
    duration = stream.get("duration") or fmt.get("duration") or ""
    return {
        "path": str(path),
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "sample_aspect_ratio": stream.get("sample_aspect_ratio", ""),
        "display_aspect_ratio": stream.get("display_aspect_ratio", ""),
        "rotation": stream_rotation(stream),
        "duration": float(duration) if duration not in {"", None} else None,
        "codec": stream.get("codec_name", ""),
        "format_name": fmt.get("format_name", ""),
        "size_bytes": int(fmt.get("size") or path.stat().st_size),
    }


def choose_strategy(summary: dict[str, Any], requested: str) -> tuple[str, str]:
    if requested != "auto":
        return requested, f"estrategia forzada: {requested}"
    dar = ratio_value(summary.get("display_aspect_ratio", ""))
    rotation = abs(int(summary.get("rotation") or 0))
    width = int(summary.get("width") or 0)
    height = int(summary.get("height") or 0)
    portrait_dar = dar is not None and 0.48 <= dar <= 0.64
    if rotation in {90, 270}:
        return "crop", "rotación declara portrait; se autorrota y se hace crop 9:16"
    if portrait_dar:
        return "crop", "DAR/SAR declara portrait; se materializa como 1080x1920 real"
    if height > width:
        return "crop", "ya parece portrait por dimensiones reales"
    return "blur", "parece landscape real; se conserva encuadre con fondo blur"


def normalize(
    input_path: Path,
    output_path: Path,
    strategy: str,
    ffmpeg_bin: str,
) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if strategy == "crop":
        video_filter = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,setsar=1,fps=30,format=yuv420p"
        )
    else:
        video_filter = (
            "split=2[bg][fg];"
            "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,gblur=sigma=36,eq=brightness=-0.05:saturation=0.85[bg];"
            "[fg]scale=1080:1920:force_original_aspect_ratio=decrease,setsar=1[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps=30,format=yuv420p"
        )
    return run_command(
        [
            ffmpeg_bin,
            "-y",
            "-i",
            str(input_path),
            "-map_metadata",
            "-1",
            "-metadata:s:v:0",
            "rotate=0",
            "-filter:v",
            video_filter,
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )


def make_preview(input_path: Path, output_path: Path, duration: float | None, ffmpeg_bin: str) -> str:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    seek = "0"
    if duration and duration > 1:
        seek = f"{min(duration * 0.45, max(duration - 0.5, 0)):.3f}"
    return run_command(
        [
            ffmpeg_bin,
            "-y",
            "-ss",
            seek,
            "-i",
            str(input_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ]
    )


def make_contact_sheet(preview_paths: list[Path], output_path: Path) -> str:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return "Pillow no está instalado; previews individuales generadas."

    if not preview_paths:
        return "No hay previews para contact sheet."

    thumbs = []
    for path in preview_paths:
        image = Image.open(path).convert("RGB")
        image.thumbnail((216, 384))
        canvas = Image.new("RGB", (216, 430), "white")
        x = (216 - image.width) // 2
        canvas.paste(image, (x, 0))
        draw = ImageDraw.Draw(canvas)
        label = path.stem.replace("_preview", "")
        font = ImageFont.load_default()
        draw.text((8, 394), label[:32], fill=(20, 20, 20), font=font)
        thumbs.append(canvas)

    columns = 3
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 216, rows * 430), "white")
    for index, thumb in enumerate(thumbs):
        x = (index % columns) * 216
        y = (index // columns) * 430
        sheet.paste(thumb, (x, y))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, quality=92)
    return str(output_path)


def visual_risk(original: dict[str, Any], strategy: str) -> str:
    rotation = abs(int(original.get("rotation") or 0))
    width = int(original.get("width") or 0)
    height = int(original.get("height") or 0)
    sar = original.get("sample_aspect_ratio") or ""
    if rotation in {90, 270}:
        return "medio: depende de que autorotate haya corregido bien"
    if sar and sar != "1:1":
        return "medio/alto: venía de SAR/DAR raro; revisar preview"
    if width == height:
        return "medio: square materializado a vertical"
    if strategy == "blur":
        return "bajo/medio: conserva encuadre, con bandas integradas"
    return "bajo"


def main() -> None:
    args = parse_args()
    ffmpeg_bin = find_binary("ffmpeg")
    ffprobe_bin = find_binary("ffprobe")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    preview_paths: list[Path] = []

    for target in catalog_targets():
        slug = slugify(target.label)
        print(f"[normalizar] {target.label}", file=sys.stderr)
        download = download_original(target, args.force_download)
        input_path = Path(download["path"])
        before_meta = ffprobe(input_path, ffprobe_bin)
        before = metadata_summary(input_path, before_meta)
        strategy, reason = choose_strategy(before, args.strategy)

        output_path = OUTPUT_DIR / f"{slug}_1080x1920_{strategy}.mp4"
        ffmpeg_log = normalize(input_path, output_path, strategy, ffmpeg_bin)
        after = metadata_summary(output_path, ffprobe(output_path, ffprobe_bin))
        preview_path = PREVIEWS_DIR / f"{slug}_{strategy}_preview.jpg"
        make_preview(output_path, preview_path, after.get("duration"), ffmpeg_bin)
        preview_paths.append(preview_path)

        fallback_path = ""
        fallback_preview = ""
        if args.also_blur_fallback and strategy != "blur":
            fallback = OUTPUT_DIR / f"{slug}_1080x1920_blur_fallback.mp4"
            normalize(input_path, fallback, "blur", ffmpeg_bin)
            fallback_meta = metadata_summary(fallback, ffprobe(fallback, ffprobe_bin))
            fallback_img = PREVIEWS_DIR / f"{slug}_blur_fallback_preview.jpg"
            make_preview(fallback, fallback_img, fallback_meta.get("duration"), ffmpeg_bin)
            preview_paths.append(fallback_img)
            fallback_path = str(fallback)
            fallback_preview = str(fallback_img)

        results.append(
            {
                "label": target.label,
                "asset_id": target.asset_id,
                "drive_url": target.url,
                "download": download,
                "strategy": strategy,
                "selection_reason": reason,
                "original": before,
                "final": after,
                "normalized_path": str(output_path),
                "preview_path": str(preview_path),
                "blur_fallback_path": fallback_path,
                "blur_fallback_preview": fallback_preview,
                "visual_risk": visual_risk(before, strategy),
                "ffmpeg_warning_excerpt": ffmpeg_log[-1200:] if ffmpeg_log else "",
            }
        )

    contact_sheet_result = make_contact_sheet(preview_paths, CONTACT_SHEET)
    report = {
        "output_dir": str(OUTPUT_DIR),
        "contact_sheet": str(CONTACT_SHEET) if CONTACT_SHEET.exists() else "",
        "contact_sheet_result": contact_sheet_result,
        "results": results,
    }
    metadata_path = OUTPUT_DIR / "metadata.json"
    metadata_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
