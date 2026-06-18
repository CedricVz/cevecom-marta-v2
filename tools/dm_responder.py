"""
tools/dm_responder.py — Servidor Flask para responder DMs de Instagram automáticamente.

Recibe eventos de Meta Webhooks, procesa el DM con OpenAI Responses API
(con contexto encadenado via previous_response_id) y responde al usuario
vía Meta Graph API. El contexto de cada usuario se persiste en SQLite.

Uso:
    python tools/dm_responder.py
    # En otra terminal:
    ngrok http 5000
"""

import hmac
import json
import logging
import os
import re
import smtplib
import sys
import threading
import unicodedata
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
from flask import Flask, abort, jsonify, request
from openai import OpenAI

from config import cfg
from tools.db_context import leer_response_id, guardar_response_id
from tools.instagram_comments import procesar_comentarios_webhook

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger("dm_responder")

META_API = "https://graph.instagram.com/v25.0"  # no usado directamente — ver _enviar_dm
WHATSAPP_RESERVAS = "656 376 435"
RESPUESTA_RESERVAS = (
    f"Para reservar cita, escríbenos por WhatsApp al {WHATSAPP_RESERVAS} "
    "y Marta o el equipo te ayudan directamente."
)

INSTRUCCIONES = """
Eres Marta, asistente virtual del centro de estética Marta Suñé Estilista & Estética Avanzada en Barcelona.
Respondes a mensajes directos de Instagram de clientes y potenciales clientes.

Tu rol:
- Informar sobre los tratamientos disponibles, precios y preguntas frecuentes
- Orientar de forma general sobre tratamientos, cuidados y contacto del centro
- Mantener un tono cercano, profesional y amable en español o catalán

Información del centro:
- Nombre: Marta Suñé Estilista & Estética Avanzada
- Ubicación: Barcelona
- Horario: martes a sábado de 10:00 a 19:30 (domingo y lunes cerrado)
- Web: martasune.es
- Contacto WhatsApp para reservas: 656 376 435

Formato y presentación (importante — Instagram se lee en móvil):
- Divide cada respuesta en bloques cortos separados por una línea en blanco.
- Máximo 2-3 frases por bloque. Nada de párrafos densos ni "muros" de texto.
- Cuando enumeres tratamientos, precios, beneficios o pasos: usa lista con guiones (-), una opción por línea.
- Usa 1 o 2 emojis por respuesta, no más, para guiar la vista (no decorar):
  ✨ presentación general · 💆‍♀️ tratamientos faciales/corporales · 📅 citas y horarios · 💬 contacto · 📍 ubicación
- Saluda solo en la primera respuesta de la conversación. Si ya tienes contexto previo con el cliente, ve directa al grano sin volver a saludar.
- Tono cercano y en segunda persona ("te aconsejo", "puedo orientarte"). Evita tecnicismos.

Instrucciones de contenido:
- Busca siempre en tu base de conocimiento antes de responder preguntas sobre
  tratamientos o precios.
- Si no encuentras la información o no puedes resolver la consulta, indica
  amablemente: "Para más información puedes escribirnos por WhatsApp al 656 376 435 o visitar martasune.es."
- Responde siempre en el mismo idioma que el cliente (español o catalán).
- Sé concisa — los mensajes de Instagram deben ser breves y directos.
- No inventes precios ni disponibilidad que no tengas confirmados.
- Si te preguntan tu identidad o el nombre del centro, eres "Marta Suñé Estilista & Estética Avanzada". Nunca menciones "Cevecom".

REGLA CRÍTICA DE RESERVAS — OBLIGATORIA:
- Nunca confirmes citas.
- Nunca inventes horarios.
- Nunca digas "te he reservado".
- Nunca digas "tienes cita".
- Nunca ofrezcas huecos concretos.
- Nunca simules tener acceso a una agenda.
- Si el cliente pide cita, reserva, horario disponible, disponibilidad, agenda, turno, hueco, quiere agendar un tratamiento, o quiere cambiar/cancelar una cita, deriva siempre a WhatsApp.
- Respuesta base para cualquier reserva/cambio/cancelación: "Para reservar cita, escríbenos por WhatsApp al 656 376 435 y Marta o el equipo te ayudan directamente."
- Puedes responder preguntas de información, precio o tratamientos. Si la conversación pasa de información a reserva real, aplica esta regla y deriva a WhatsApp.
""".strip()

openai_client = OpenAI(api_key=cfg.openai_api_key)


# ── Reglas deterministas ─────────────────────────────────────────────────────

def _normalizar_texto(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )


def _mensaje_es_reserva(mensaje: str) -> bool:
    """Detecta intención de reserva/cita para derivar sin pasar por el modelo."""
    texto = _normalizar_texto(mensaje)
    patrones = [
        r"\bpedir\s+cita\b",
        r"\bcita\b",
        r"\bcitas\b",
        r"\breserv",
        r"\bagend",
        r"\bturno\b",
        r"\bhueco\b",
        r"\bdisponib",
        r"\bhorario\s+disponible\b",
        r"\ba\s+que\s+hora\s+puedo\s+ir\b",
        r"\ba\s+que\s+hora\b.*\b(ir|venir|pasar)\b",
        r"\bpuedo\s+ir\b",
        r"\bpuedo\s+venir\b",
        r"\bpuedo\s+pasar\b",
        r"\bpara\s+(hoy|manana|viernes|sabado|lunes|martes|miercoles|jueves|domingo)\b",
        r"\b(hoy|manana|viernes|sabado|lunes|martes|miercoles|jueves|domingo)\b.*\b(hueco|disponible|cita|reserv|venir|ir|pasar)\b",
        r"\b(cancelar|cambiar|mover|modificar)\b.*\bcita\b",
        r"\bcita\b.*\b(cancelar|cambiar|mover|modificar)\b",
    ]
    return any(re.search(patron, texto) for patron in patrones)


# ── OpenAI Responses API ───────────────────────────────────────────────────────

def _llamar_openai(mensaje: str, prev_response_id: Optional[str]) -> tuple:
    """Llama a la Responses API y devuelve (texto_respuesta, nuevo_response_id)."""
    kwargs: dict = {
        "model": "gpt-4o",
        "instructions": INSTRUCCIONES,
        "input": mensaje,
        "tools": [
            {
                "type": "file_search",
                "vector_store_ids": [cfg.openai_vector_store_id],
            }
        ],
    }
    if prev_response_id:
        kwargs["previous_response_id"] = prev_response_id

    response = openai_client.responses.create(**kwargs)
    return response.output_text, response.id


# ── Meta Graph API ─────────────────────────────────────────────────────────────

def _enviar_dm(sender_id: str, texto: str) -> None:
    r = requests.post(
        "https://graph.instagram.com/v25.0/me/messages",
        headers={
            "Authorization": f"Bearer {cfg.instagram_api_token}",
            "Content-Type": "application/json",
        },
        json={
            "recipient": {"id": sender_id},
            "message": {"text": texto},
            "messaging_type": "RESPONSE",
        },
        timeout=30,
    )
    r.raise_for_status()


# ── Notificación de error ──────────────────────────────────────────────────────

def _notificar_error(sender_id: str, mensaje_cliente: str, error: str) -> None:
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        msg = EmailMessage()
        msg["Subject"] = f"[Cevecom DMs] Error respondiendo a {sender_id}"
        msg["From"]    = cfg.email_smtp_user
        msg["To"]      = cfg.email_copia_prestador
        msg.set_content(
            f"Error al responder DM de Instagram.\n\n"
            f"Usuario Instagram: {sender_id}\n"
            f"Mensaje recibido: {mensaje_cliente}\n"
            f"Error: {error}\n"
            f"Hora: {timestamp}\n"
        )
        with smtplib.SMTP(cfg.email_smtp_host, cfg.email_smtp_port) as s:
            s.ehlo()
            s.starttls()
            s.login(cfg.email_smtp_user, cfg.email_smtp_password)
            s.send_message(msg)
        logger.info("Email de error enviado a %s", cfg.email_copia_prestador)
    except Exception as e:
        logger.error("No se pudo enviar email de error: %s", e)


# ── Procesamiento en background ────────────────────────────────────────────────

def _procesar_dm(sender_id: str, mensaje: str) -> None:
    try:
        if _mensaje_es_reserva(mensaje):
            _enviar_dm(sender_id, RESPUESTA_RESERVAS)
            logger.info("DM de reserva derivado a WhatsApp → sender=%s", sender_id)
            return

        prev_id = leer_response_id(sender_id)
        respuesta, nuevo_id = _llamar_openai(mensaje, prev_id)
        guardar_response_id(sender_id, nuevo_id)
        _enviar_dm(sender_id, respuesta)
        logger.info("DM respondido → sender=%s | prev=%s → nuevo=%s", sender_id, prev_id, nuevo_id)
    except Exception as e:
        logger.error("Error procesando DM de %s: %s: %s", sender_id, type(e).__name__, e)
        _notificar_error(sender_id, mensaje, f"{type(e).__name__}: {e}")


# ── Flask ──────────────────────────────────────────────────────────────────────

app = Flask(__name__)


@app.route("/healthz", methods=["GET"])
def healthz():
    """Healthcheck sin auth — usado por Railway para verificar el servicio."""
    return jsonify({"status": "ok"}), 200


@app.route("/webhook", methods=["GET"])
def verificar_webhook():
    """Endpoint de verificación que Meta llama al configurar el webhook."""
    mode      = request.args.get("hub.mode")
    token     = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == cfg.meta_webhook_verify_token:
        logger.info("Webhook verificado por Meta.")
        return challenge, 200

    logger.warning("Verificación fallida — mode=%s, token recibido no coincide.", mode)
    abort(403)


@app.route("/webhook", methods=["POST"])
def recibir_evento():
    """Recibe eventos de Instagram. Responde 200 inmediatamente y procesa en background."""
    # Verificar firma HMAC-SHA256 (presente en producción, ausente en test local)
    firma_cabecera = request.headers.get("X-Hub-Signature-256", "")
    if firma_cabecera:
        esperada = "sha256=" + hmac.new(
            cfg.facebook_app_secret.encode(),
            request.data,
            "sha256",
        ).hexdigest()
        if not hmac.compare_digest(firma_cabecera, esperada):
            logger.warning("Firma HMAC inválida — request rechazada.")
            abort(401)

    body = request.get_json(force=True, silent=True) or {}
    logger.debug("Evento recibido: %s", json.dumps(body)[:500])
    if not isinstance(body, dict):
        logger.warning("Payload Meta ignorado: body no es objeto JSON.")
        return jsonify({"status": "ok"}), 200

    entries = body.get("entry", [])
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        logger.warning("Payload Meta ignorado parcialmente: entry no es lista.")
        entries = []

    for entry in entries:
        if not isinstance(entry, dict):
            logger.warning("Entry Meta ignorado: no es objeto.")
            continue

        messaging = entry.get("messaging", [])
        if messaging is None:
            messaging = []
        if not isinstance(messaging, list):
            logger.warning("Entry Meta ignorado para DMs: messaging no es lista.")
            messaging = []

        for evento in messaging:
            if not isinstance(evento, dict):
                logger.warning("Evento DM ignorado: no es objeto.")
                continue
            sender = evento.get("sender") or {}
            message = evento.get("message") or {}
            if not isinstance(sender, dict) or not isinstance(message, dict):
                logger.warning("Evento DM ignorado: sender/message no son objetos.")
                continue
            sender_id = sender.get("id", "")
            mensaje   = message.get("text", "")

            if not sender_id or not mensaje:
                continue
            # Ignorar ecos de mensajes propios
            if sender_id == cfg.instagram_user_id:
                continue

            logger.info("DM recibido de %s: %.60s", sender_id, mensaje)
            threading.Thread(
                target=_procesar_dm,
                args=(sender_id, mensaje),
                daemon=True,
            ).start()

    try:
        procesar_comentarios_webhook(body, async_mode=True)
    except Exception as e:
        logger.error("Error enrutando comentarios: %s: %s", type(e).__name__, e)

    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info("dm_responder arrancando en http://localhost:%d", port)
    logger.info(
        "Para pruebas locales con Meta, expón el endpoint con: ngrok http %d  "
        "→ configura la URL en Facebook App → Webhooks",
        port,
    )
    app.run(host="0.0.0.0", port=port, debug=False)
