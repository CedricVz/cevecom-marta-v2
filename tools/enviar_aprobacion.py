"""
tools/enviar_aprobacion.py — Envía el vídeo a Marta para aprobación por email.

Lee JSON desde stdin (salida de generar_video.py), genera un token único
por fila, envía un email HTML con el vídeo y botones de aprobación/rechazo,
actualiza Google Sheets y pasa el JSON enriquecido a stdout.

Uso:
    python tools/generar_video.py | python tools/enviar_aprobacion.py
    echo '[{"fila":2,"video_url":"...","tema":"...","tratamiento":"..."}]' | python tools/enviar_aprobacion.py
"""

import json
import logging
import secrets
import smtplib
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import gspread
from gspread.utils import rowcol_to_a1

from config import cfg
from tools._columnas import COL
from tools.google_creds import service_account_credentials

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger("enviar_aprobacion")

SCOPES_WRITE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# ── Plantillas de email ───────────────────────────────────────────────────────

_HTML = """\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f2f2f2;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f2f2f2;padding:32px 0;">
  <tr><td align="center">
    <table width="580" cellpadding="0" cellspacing="0"
           style="background:#ffffff;border-radius:8px;overflow:hidden;
                  box-shadow:0 2px 10px rgba(0,0,0,.08);">

      <!-- Cabecera -->
      <tr>
        <td style="background:#1a1a2e;padding:24px 32px;">
          <p style="margin:0;color:#ffffff;font-size:20px;font-weight:700;
                    letter-spacing:.5px;">Cevecom Marta</p>
          <p style="margin:4px 0 0;color:#9ba5c9;font-size:13px;">Sistema de Reels</p>
        </td>
      </tr>

      <!-- Cuerpo -->
      <tr>
        <td style="padding:32px;">
          <p style="margin:0 0 6px;color:#222;font-size:16px;">Hola Marta,</p>
          <p style="margin:0 0 28px;color:#555;font-size:15px;line-height:1.6;">
            Tu nuevo Reel est&aacute; listo. Rev&iacute;salo y dinos si lo publicamos.
          </p>

          <!-- Ficha del contenido -->
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="background:#f8f9fa;border-radius:6px;margin-bottom:28px;">
            <tr>
              <td style="padding:18px 22px;">
                <p style="margin:0 0 4px;color:#999;font-size:11px;
                          text-transform:uppercase;letter-spacing:.8px;">Tema</p>
                <p style="margin:0 0 16px;color:#1a1a2e;font-size:16px;font-weight:700;">
                  {tema}
                </p>
                <p style="margin:0 0 4px;color:#999;font-size:11px;
                          text-transform:uppercase;letter-spacing:.8px;">Tratamiento</p>
                <p style="margin:0;color:#555;font-size:14px;line-height:1.5;">
                  {tratamiento}
                </p>
              </td>
            </tr>
          </table>

          <!-- Botón ver vídeo -->
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:36px;">
            <tr>
              <td align="center">
                <a href="{video_url}"
                   style="display:inline-block;padding:14px 36px;
                          background:#0055cc;color:#ffffff;font-size:15px;
                          font-weight:700;text-decoration:none;border-radius:6px;">
                  &#9654;&#xFE0E;&nbsp; Ver el v&iacute;deo
                </a>
              </td>
            </tr>
          </table>

          <!-- Pregunta aprobación -->
          <p style="margin:0 0 18px;color:#222;font-size:15px;font-weight:700;
                    text-align:center;">&iquest;Lo publicamos en Instagram?</p>

          <!-- Botones aprobación / rechazo -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr>
              <td width="48%" align="center">
                <a href="{url_aprobar}"
                   style="display:inline-block;width:100%;max-width:210px;
                          padding:14px 0;background:#28a745;color:#ffffff;
                          font-size:15px;font-weight:700;text-decoration:none;
                          border-radius:6px;text-align:center;box-sizing:border-box;">
                  &#10003;&nbsp; S&iacute;, publicar
                </a>
              </td>
              <td width="4%"></td>
              <td width="48%" align="center">
                <a href="{url_rechazar}"
                   style="display:inline-block;width:100%;max-width:210px;
                          padding:14px 0;background:#dc3545;color:#ffffff;
                          font-size:15px;font-weight:700;text-decoration:none;
                          border-radius:6px;text-align:center;box-sizing:border-box;">
                  &#10005;&nbsp; No, rechazar
                </a>
              </td>
            </tr>
          </table>

          <p style="margin:28px 0 0;color:#bbb;font-size:12px;text-align:center;
                    line-height:1.6;">
            Si los botones no funcionan, abre este enlace en el navegador:<br>
            <a href="{video_url}" style="color:#0055cc;">{video_url}</a>
          </p>
        </td>
      </tr>

      <!-- Pie -->
      <tr>
        <td style="padding:16px 32px;background:#f8f9fa;border-top:1px solid #e9ecef;">
          <p style="margin:0;color:#bbb;font-size:11px;text-align:center;">
            Cevecom Marta &middot; Sistema automatizado de contenido
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""

_TEXTO = """\
Hola Marta,

Tu nuevo Reel está listo:

  TEMA:        {tema}
  TRATAMIENTO: {tratamiento}

Ver el vídeo:
  {video_url}

¿Lo publicamos en Instagram?

  Sí, publicar → {url_aprobar}
  No, rechazar → {url_rechazar}

--
Cevecom Marta · Sistema automatizado de contenido
"""


# ── Google Sheets ─────────────────────────────────────────────────────────────

def conectar_sheets() -> gspread.Worksheet:
    creds = service_account_credentials(SCOPES_WRITE)
    gc = gspread.authorize(creds)
    return gc.open_by_key(cfg.google_sheets_id).sheet1


def actualizar_fila(hoja: gspread.Worksheet, fila: int, updates: dict[str, str]) -> None:
    payload = [
        {"range": rowcol_to_a1(fila, col), "values": [[valor]]}
        for nombre, valor in updates.items()
        if (col := COL.get(nombre)) is not None
    ]
    if payload:
        hoja.batch_update(payload)


def leer_reintentos(hoja: gspread.Worksheet, fila: int) -> int:
    try:
        valor = hoja.cell(fila, COL["Reintentos"]).value
        return int(valor) if valor else 0
    except Exception:
        return 0


# ── Email ─────────────────────────────────────────────────────────────────────

def construir_urls(token: str) -> tuple[str, str]:
    base = cfg.apps_script_webhook_url
    return (
        f"{base}?token={token}&decision=aprobado",
        f"{base}?token={token}&decision=rechazado",
    )


def enviar_email(item: dict, token: str) -> None:
    url_aprobar, url_rechazar = construir_urls(token)

    vars_ = {
        "tema":        item["tema"],
        "tratamiento": item.get("tratamiento", ""),
        "video_url":   item["video_url"],
        "url_aprobar": url_aprobar,
        "url_rechazar": url_rechazar,
    }

    msg = EmailMessage()
    msg["Subject"] = f"Reel listo para revisar: {item['tema']}"
    msg["From"]    = cfg.email_smtp_user
    msg["To"]      = cfg.email_destinatario
    msg["Cc"]      = cfg.email_copia_prestador

    msg.set_content(_TEXTO.format(**vars_))
    msg.add_alternative(_HTML.format(**vars_), subtype="html")

    with smtplib.SMTP(cfg.email_smtp_host, cfg.email_smtp_port) as server:
        server.starttls()
        server.login(cfg.email_smtp_user, cfg.email_smtp_password)
        server.sendmail(
            cfg.email_smtp_user,
            [cfg.email_destinatario, cfg.email_copia_prestador],
            msg.as_bytes(),
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _registrar_error(hoja: gspread.Worksheet, fila: int, mensaje: str) -> None:
    try:
        reintentos = leer_reintentos(hoja, fila) + 1
    except Exception:
        reintentos = 1
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    actualizar_fila(hoja, fila, {
        "Estado":    "Error",
        "Errores":   f"{timestamp} | {mensaje}",
        "Reintentos": str(reintentos),
    })


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        logger.error("No se recibió JSON por stdin.")
        sys.exit(1)

    try:
        items: list[dict] = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("JSON inválido en stdin: %s", e)
        sys.exit(1)

    if not items:
        logger.info("0 vídeos recibidos. Nada que procesar.")
        print("[]")
        return

    try:
        hoja = conectar_sheets()
    except Exception as e:
        logger.error("Error conectando a Google Sheets: %s", e)
        sys.exit(1)

    resultados = []

    for item in items:
        fila = item["fila"]
        logger.info("Fila %d → enviando email de aprobación: %s", fila, item["tema"])

        try:
            token = secrets.token_urlsafe(32)
            enviar_email(item, token)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
            actualizar_fila(hoja, fila, {
                "Email_enviado":    timestamp,
                "Token_aprobacion": token,
                "Errores":          "",
            })

            resultados.append({**item, "token": token})
            logger.info("Fila %d: OK — email enviado a %s", fila, cfg.email_destinatario)

        except smtplib.SMTPException as e:
            logger.error("Fila %d: error SMTP — %s", fila, e)
            _registrar_error(hoja, fila, f"SMTP: {e}")

        except Exception as e:
            logger.error("Fila %d: error inesperado — %s: %s", fila, type(e).__name__, e)
            _registrar_error(hoja, fila, f"{type(e).__name__}: {e}")

    logger.info(
        "%d/%d emails enviados con éxito.",
        len(resultados),
        len(items),
    )
    print(json.dumps(resultados, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
