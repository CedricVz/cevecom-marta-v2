"""
tools/postprocesar_video.py — Postproducción local de Reels.

Fase inicial: modo `logo_only`.

No llama a HeyGen, Google Sheets, email ni Meta. Recibe un MP4 local y genera
otro MP4 local con el logo de marca solo al final. Requiere ffmpeg/ffprobe en
PATH.
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOGO = REPO_ROOT / "assets" / "logo_marta.webp"
DEFAULT_OUTPUT = REPO_ROOT / "videos_generados" / "marta_lanzamiento_logo_final.mp4"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Postprocesa un Reel local con ffmpeg.")
    parser.add_argument("--mode", choices=["logo_only", "full"], required=True)
    parser.add_argument("--input", required=True, help="Ruta local del MP4 base.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Ruta del MP4 final.")
    parser.add_argument("--logo", default=str(DEFAULT_LOGO), help="Ruta del logo.")
    parser.add_argument("--final-seconds", type=float, default=2.0)
    parser.add_argument("--logo-width-ratio", type=float, default=0.34)
    parser.add_argument("--bottom-margin", type=int, default=110)
    parser.add_argument(
        "--extend-final-hold",
        action="store_true",
        help="Extiende el último frame final-seconds con tpad antes de añadir el logo.",
    )
    return parser.parse_args()


def require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(
            f"No se encontró {name} en PATH. Instala ffmpeg y asegúrate de que "
            f"{name}.exe sea accesible desde la terminal."
        )
    return path


def ffprobe_duration(ffprobe: str, input_path: Path) -> float:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(input_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def run_logo_only(args: argparse.Namespace) -> dict:
    ffmpeg = require_binary("ffmpeg")
    ffprobe = require_binary("ffprobe")

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    logo_path = Path(args.logo).resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"No existe el MP4 de entrada: {input_path}")
    if not logo_path.exists():
        raise FileNotFoundError(f"No existe el logo: {logo_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = ffprobe_duration(ffprobe, input_path)
    final_seconds = max(args.final_seconds, 0.1)
    overlay_start = duration if args.extend_final_hold else max(duration - final_seconds, 0)

    base_filters = [
        "scale=720:1280:force_original_aspect_ratio=decrease",
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2",
        "setsar=1",
    ]
    if args.extend_final_hold:
        base_filters.append(f"tpad=stop_mode=clone:stop_duration={final_seconds}")

    logo_width = max(1, int(720 * args.logo_width_ratio))
    filter_complex = (
        f"[0:v]{','.join(base_filters)}[base];"
        f"[1:v]format=rgba,scale={logo_width}:-1[logo];"
        f"[base][logo]overlay=x=(W-w)/2:y=H-h-{args.bottom_margin}:"
        f"enable='gte(t,{overlay_start:.3f})'[v]"
    )

    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-i",
        str(logo_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    output_duration = ffprobe_duration(ffprobe, output_path)

    return {
        "mode": "logo_only",
        "input": str(input_path),
        "output": str(output_path),
        "logo": str(logo_path),
        "input_duration_seconds": round(duration, 3),
        "output_duration_seconds": round(output_duration, 3),
        "logo_visible_from_second": round(overlay_start, 3),
        "logo_visible_seconds": round(output_duration - overlay_start, 3),
        "extended_final_hold": bool(args.extend_final_hold),
        "command": cmd,
    }


def main() -> None:
    args = parse_args()

    if args.mode == "full":
        raise SystemExit(
            "Modo full aún no está implementado. Usa --mode logo_only para esta fase."
        )

    try:
        result = run_logo_only(args)
    except Exception as e:
        print(f"[postprocesar_video] ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
