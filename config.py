"""
config.py — Carga y valida todas las variables de entorno.

Importa este módulo antes que cualquier otro:
    from config import cfg
    print(cfg.anthropic_api_key)

Si falta cualquier variable requerida, el proceso termina con un
mensaje claro indicando exactamente qué falta y cómo conseguirlo.
"""

import io
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

if sys.stdin  and hasattr(sys.stdin,  "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8")
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

logger = logging.getLogger(__name__)

# Variables que el usuario debe rellenar obligatoriamente.
# Formato: (NOMBRE_VARIABLE, pista para el mensaje de error)
_REQUIRED: list[tuple[str, str]] = [
    # Módulo 1 — Reels
    ("ANTHROPIC_API_KEY",       "Clave de Anthropic — console.anthropic.com → API Keys"),
    ("HEYGEN_API_KEY",          "API token de HeyGen — app.heygen.com → Settings → API"),
    ("GOOGLE_SHEETS_ID",        "ID de la hoja de Sheets (parte de la URL entre /d/ y /edit)"),
    ("EMAIL_SMTP_USER",         "Cuenta Gmail del remitente (ej: cevecom@gmail.com)"),
    ("EMAIL_SMTP_PASSWORD",     "Contraseña de aplicación de Gmail (16 caracteres sin espacios)"),
    ("EMAIL_DESTINATARIO",      "Email de Marta — recibirá los vídeos para aprobar"),
    ("EMAIL_COPIA_PRESTADOR",   "Email de Cedric — copia de todo, incluidos errores técnicos"),
    ("APPS_SCRIPT_WEBHOOK_URL", "URL del Apps Script de aprobación — script.google.com"),
    ("FACEBOOK_APP_ID",         "ID de la Facebook App — developers.facebook.com/apps"),
    ("FACEBOOK_APP_SECRET",     "Clave secreta de la Facebook App"),
    ("FACEBOOK_PAGE_ID",        "ID de la Página de Facebook conectada a Instagram"),
    ("INSTAGRAM_USER_ID",       "ID de la cuenta Instagram Business de Marta"),
    ("FACEBOOK_ACCESS_TOKEN",   "Token de acceso de Meta (60 días) — tools/renovar_token_meta.py"),
    # Módulo 2 — Agente de DMs
    ("OPENAI_API_KEY",            "Clave de OpenAI — platform.openai.com/api-keys"),
    ("OPENAI_VECTOR_STORE_ID",    "ID del vector store con info del centro (ya creado)"),
    ("OPENAI_ASSISTANT_ID",       "ID del Assistant de OpenAI (ya creado)"),
    ("META_WEBHOOK_VERIFY_TOKEN", "Token secreto para verificar el webhook de Meta — elige cualquier string aleatorio"),
    ("INSTAGRAM_API_TOKEN",       "Token de Instagram para DMs — generado en Meta Developers"),
]


@dataclass(frozen=True)
class Config:
    # Anthropic
    anthropic_api_key: str

    # HeyGen
    heygen_api_key: str

    # Google Sheets
    google_sheets_id: str
    calendario_marta_sheets_id: Optional[str]  # hoja independiente de Marta (pipeline v3)
    google_credentials_path: Path

    # Email
    email_smtp_host: str
    email_smtp_port: int
    email_smtp_user: str
    email_smtp_password: str
    email_destinatario: str
    email_copia_prestador: str

    # Apps Script (webhook de aprobación)
    apps_script_webhook_url: str

    # Meta / Instagram
    facebook_app_id: str
    facebook_app_secret: str
    facebook_page_id: str
    instagram_user_id: str
    facebook_access_token: str
    facebook_access_token_expiry: Optional[date]  # None hasta la primera renovación

    # Módulo 2 — Agente de DMs
    openai_api_key: str
    openai_vector_store_id: str
    openai_assistant_id: str
    meta_webhook_verify_token: str
    instagram_api_token: str


def load() -> Config:
    load_dotenv()

    # ── 1. Variables obligatorias ─────────────────────────────────────────────
    missing = [
        f"  {var:<35} # {hint}"
        for var, hint in _REQUIRED
        if not os.getenv(var, "").strip()
    ]
    if missing:
        sys.exit(
            f"\n[config] Faltan {len(missing)} variable(s) en el .env:\n\n"
            + "\n".join(missing)
            + "\n\nCopia .env.example como .env y rellena cada valor.\n"
        )

    # ── 2. Credenciales Google: archivo en disco O variable de entorno ───────
    # Local: GOOGLE_CREDENTIALS_PATH apunta al .json en disco.
    # Railway: GOOGLE_CREDENTIALS_JSON contiene el .json como string.
    # tools/google_creds.py prefiere la variable; si no, usa la ruta.
    creds_path = Path(os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json"))
    has_creds_json = bool(os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip())
    if not has_creds_json and not creds_path.exists():
        sys.exit(
            f"\n[config] No hay credenciales de Google disponibles:\n"
            f"  - GOOGLE_CREDENTIALS_JSON no está definida (modo Railway), y\n"
            f"  - {creds_path.resolve()} no existe en disco (modo local).\n\n"
            f"Define una de las dos. Consulta .env.example para instrucciones.\n"
        )

    # ── 3. EMAIL_SMTP_PORT — debe ser entero ─────────────────────────────────
    raw_port = os.getenv("EMAIL_SMTP_PORT", "587")
    try:
        smtp_port = int(raw_port)
    except ValueError:
        sys.exit(
            f"\n[config] EMAIL_SMTP_PORT debe ser un número entero.\n"
            f"  Valor actual: '{raw_port}'\n"
            f"  Valor correcto para Gmail: 587\n"
        )

    # ── 4. FACEBOOK_ACCESS_TOKEN_EXPIRY — opcional, validar formato y vigencia
    raw_expiry = os.getenv("FACEBOOK_ACCESS_TOKEN_EXPIRY", "").strip()
    token_expiry: Optional[date] = None
    if raw_expiry:
        try:
            token_expiry = datetime.strptime(raw_expiry, "%Y-%m-%d").date()
        except ValueError:
            sys.exit(
                f"\n[config] FACEBOOK_ACCESS_TOKEN_EXPIRY tiene formato incorrecto.\n"
                f"  Valor actual: '{raw_expiry}'\n"
                f"  Formato requerido: YYYY-MM-DD (ej: 2025-06-30)\n"
            )
        days_left = (token_expiry - date.today()).days
        if days_left < 0:
            logger.warning(
                "[config] ⚠️  El token de Meta EXPIRÓ hace %d día(s). "
                "Ejecuta tools/renovar_token_meta.py urgentemente.",
                abs(days_left),
            )
        elif days_left < 10:
            logger.warning(
                "[config] ⚠️  El token de Meta expira en %d día(s). "
                "Ejecuta tools/renovar_token_meta.py antes de que expire.",
                days_left,
            )

    return Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        heygen_api_key=os.environ["HEYGEN_API_KEY"],
        google_sheets_id=os.environ["GOOGLE_SHEETS_ID"],
        calendario_marta_sheets_id=os.getenv("CALENDARIO_MARTA_SHEETS_ID") or None,
        google_credentials_path=creds_path,
        email_smtp_host=os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com"),
        email_smtp_port=smtp_port,
        email_smtp_user=os.environ["EMAIL_SMTP_USER"],
        email_smtp_password=os.environ["EMAIL_SMTP_PASSWORD"],
        email_destinatario=os.environ["EMAIL_DESTINATARIO"],
        email_copia_prestador=os.environ["EMAIL_COPIA_PRESTADOR"],
        apps_script_webhook_url=os.environ["APPS_SCRIPT_WEBHOOK_URL"],
        facebook_app_id=os.environ["FACEBOOK_APP_ID"],
        facebook_app_secret=os.environ["FACEBOOK_APP_SECRET"],
        facebook_page_id=os.environ["FACEBOOK_PAGE_ID"],
        instagram_user_id=os.environ["INSTAGRAM_USER_ID"],
        facebook_access_token=os.environ["FACEBOOK_ACCESS_TOKEN"],
        facebook_access_token_expiry=token_expiry,
        openai_api_key=os.environ["OPENAI_API_KEY"],
        openai_vector_store_id=os.environ["OPENAI_VECTOR_STORE_ID"],
        openai_assistant_id=os.environ["OPENAI_ASSISTANT_ID"],
        meta_webhook_verify_token=os.environ["META_WEBHOOK_VERIFY_TOKEN"],
        instagram_api_token=os.getenv("INSTAGRAM_API_TOKEN", os.environ["FACEBOOK_ACCESS_TOKEN"]),
    )


# Singleton: se valida una única vez al importar el módulo.
# Si algo falla, el proceso termina aquí con un mensaje claro.
cfg = load()
