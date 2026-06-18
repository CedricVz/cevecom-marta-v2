"""Safe Instagram public comment processing.

This module is intentionally separate from the DM agent. It only handles
Instagram webhook changes whose field is ``comments`` and publishes replies
when the explicit production flag is enabled.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import requests

from config import cfg
from tools.db_context import (
    marcar_comment_estado,
    registrar_comment_recibido,
)

logger = logging.getLogger("instagram_comments")

META_API = "https://graph.instagram.com/v25.0"
WHATSAPP_RESERVAS = "656 376 435"
WHATSAPP_RESERVAS_URL = "https://wa.me/34656376435"


@dataclass(frozen=True)
class InstagramCommentEvent:
    comment_id: str
    text: str
    author_id: Optional[str] = None
    author_username: Optional[str] = None
    media_id: Optional[str] = None


@dataclass(frozen=True)
class CommentDecision:
    classification: str
    should_reply: bool
    response_text: Optional[str]
    status_when_skipped: str = "needs_review"


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on", "si", "sí"}


def comments_enabled() -> bool:
    return _env_flag("INSTAGRAM_COMMENTS_ENABLED", default=False)


def comments_dry_run() -> bool:
    return _env_flag("INSTAGRAM_COMMENTS_DRY_RUN", default=True)


def _normalizar_texto(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto.lower())
        if unicodedata.category(c) != "Mn"
    )


def _matches(texto: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, texto) for pattern in patterns)


def _extraer_comment_event(value: dict[str, Any]) -> Optional[InstagramCommentEvent]:
    comment_id = str(value.get("id") or value.get("comment_id") or "").strip()
    text = str(value.get("text") or value.get("message") or "").strip()
    if not comment_id or not text:
        logger.info("Comentario ignorado: faltan comment_id o texto.")
        return None

    from_obj = value.get("from") or {}
    media_obj = value.get("media") or {}
    if not isinstance(from_obj, dict):
        from_obj = {}
    if not isinstance(media_obj, dict):
        media_obj = {}
    author_id = str(from_obj.get("id") or value.get("from_id") or "").strip() or None
    author_username = (
        str(from_obj.get("username") or value.get("username") or "").strip() or None
    )
    media_id = str(media_obj.get("id") or value.get("media_id") or "").strip() or None

    return InstagramCommentEvent(
        comment_id=comment_id,
        text=text,
        author_id=author_id,
        author_username=author_username,
        media_id=media_id,
    )


def iter_comment_events(body: dict[str, Any]) -> Iterable[InstagramCommentEvent]:
    """Yield Instagram comment webhook events from a Meta webhook body."""
    if not isinstance(body, dict):
        logger.info("Payload de comentarios ignorado: body no es objeto JSON.")
        return

    entries = body.get("entry", [])
    if entries is None:
        return
    if not isinstance(entries, list):
        logger.info("Payload de comentarios ignorado: entry no es lista.")
        return

    for entry in entries:
        if not isinstance(entry, dict):
            logger.info("Entrada de webhook ignorada: entry no es objeto.")
            continue

        changes = entry.get("changes", [])
        if changes is None:
            continue
        if not isinstance(changes, list):
            logger.info("Entrada de comentarios ignorada: changes no es lista.")
            continue

        for change in changes:
            if not isinstance(change, dict):
                logger.info("Cambio de webhook ignorado: change no es objeto.")
                continue
            if change.get("field") != "comments":
                continue
            value = change.get("value")
            if not isinstance(value, dict):
                logger.info("Cambio de comentario ignorado: value no es objeto.")
                continue
            event = _extraer_comment_event(value)
            if event:
                yield event


def clasificar_comentario(text: str) -> CommentDecision:
    """Classify a public comment with conservative deterministic rules."""
    original = text.strip()
    normalized = _normalizar_texto(original)

    if not re.search(r"[a-z0-9]", normalized) or len(normalized) < 2:
        return CommentDecision("sin_significado", False, None, "ignored")

    spam_patterns = [
        r"https?://",
        r"\b(bit\.ly|t\.me|telegram|crypto|forex|inversion|seguidores|followers)\b",
        r"\b(sorteo|premio|gift|giveaway)\b",
        r"\b(dm\s+me|promociona|publicidad)\b",
    ]
    if _matches(normalized, spam_patterns):
        return CommentDecision("spam", False, None, "ignored")

    complaint_patterns = [
        r"\b(queja|reclam|denuncia|estafa|decepcion|decepcionada|fatal|horrible)\b",
        r"\b(mala\s+experiencia|mal\s+servicio|no\s+me\s+ha\s+gustado)\b",
        r"\b(no\s+me\s+devolve|devolucion|dinero)\b",
        r"\b(insulto|vergonzoso|mentira)\b",
    ]
    if _matches(normalized, complaint_patterns):
        return CommentDecision("queja_reclamacion", False, None, "needs_review")

    sensitive_patterns = [
        r"\b(dolor|me\s+duele|quemadur|quemad[ao]s?|infeccion|infectad)\b",
        r"\b(alergia|reaccion|efecto\s+secundario|advers[ao]|hinchad)\b",
        r"\b(sangre|herida|cicatriz|medic[ao]|dermatolog|embaraz)\b",
        r"\b(cancer|diabetes|antibiotico|anticoagulante)\b",
    ]
    if _matches(normalized, sensitive_patterns):
        return CommentDecision("medico_sensible", False, None, "needs_review")

    insult_patterns = [
        r"\b(tonta|idiota|imbecil|asco|mierda|gilipoll)\b",
    ]
    if _matches(normalized, insult_patterns):
        return CommentDecision("insulto", False, None, "ignored")

    reservation_patterns = [
        r"\b(pedir\s+cita|cita|reserv|agend|turno|hueco|disponib)\b",
        r"\b(puedo\s+(ir|venir|pasar)|quiero\s+venir)\b",
    ]
    if _matches(normalized, reservation_patterns):
        return CommentDecision(
            "reserva",
            True,
            (
                "Para reservar cita, escríbenos por WhatsApp: "
                f"{WHATSAPP_RESERVAS_URL}"
            ),
        )

    gratitude_patterns = [
        r"\b(gracias|muchas\s+gracias|genial|perfecto|super|súper)\b",
    ]
    if _matches(normalized, gratitude_patterns):
        return CommentDecision(
            "agradecimiento",
            True,
            "Gracias a ti por comentar.",
        )

    compliment_patterns = [
        r"\b(felicidades|enhorabuena|precioso|me\s+encanta|me\s+gusta)\b",
        r"\b(que\s+bonito|que\s+bien|resultado\s+bonito|espectacular)\b",
    ]
    if _matches(normalized, compliment_patterns):
        return CommentDecision(
            "felicitacion",
            True,
            "Muchas gracias. Nos alegra mucho que te guste.",
        )

    info_patterns = [
        r"\?",
        r"\b(info|informacion|precio|cuanto|tratamiento|servicio|facial|corporal)\b",
        r"\b(hifu|botox|maderoterapia|drenaje|laser|depilacion|limpieza)\b",
    ]
    if _matches(normalized, info_patterns):
        return CommentDecision(
            "consulta_general",
            True,
            (
                "Gracias por escribirnos. Para darte la información adecuada, "
                f"puedes contactarnos por WhatsApp: {WHATSAPP_RESERVAS_URL}"
            ),
        )

    if len(normalized.split()) < 3:
        return CommentDecision("sin_significado", False, None, "ignored")

    return CommentDecision("no_seguro", False, None, "needs_review")


def _graph_error_resumen(error: Exception) -> str:
    response = getattr(error, "response", None)
    if response is not None:
        status = getattr(response, "status_code", "unknown")
        return f"{type(error).__name__}: HTTP {status}"
    return f"{type(error).__name__}: {error}"


def _responder_comentario_publico(comment_id: str, message: str) -> dict[str, Any]:
    response = requests.post(
        f"{META_API}/{comment_id}/replies",
        params={"access_token": cfg.instagram_api_token},
        data={"message": message},
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    if "error" in body:
        raise RuntimeError(f"Meta API error: {body['error']}")
    return body


def procesar_comment_event(event: InstagramCommentEvent) -> None:
    if event.author_id and event.author_id == cfg.instagram_user_id:
        if registrar_comment_recibido(
            event.comment_id,
            event.media_id,
            event.author_id,
            event.author_username,
            event.text,
        ):
            marcar_comment_estado(event.comment_id, "ignored_own_account")
        logger.info("Comentario propio ignorado -> comment_id=%s", event.comment_id)
        return

    is_new = registrar_comment_recibido(
        event.comment_id,
        event.media_id,
        event.author_id,
        event.author_username,
        event.text,
    )
    if not is_new:
        logger.info("Comentario duplicado ignorado -> comment_id=%s", event.comment_id)
        return

    decision = clasificar_comentario(event.text)
    if not decision.should_reply or not decision.response_text:
        marcar_comment_estado(
            event.comment_id,
            decision.status_when_skipped,
            classification=decision.classification,
        )
        logger.info(
            "Comentario no respondido -> comment_id=%s classification=%s status=%s",
            event.comment_id,
            decision.classification,
            decision.status_when_skipped,
        )
        return

    if not comments_enabled() or comments_dry_run():
        marcar_comment_estado(
            event.comment_id,
            "dry_run",
            classification=decision.classification,
            response_text=decision.response_text,
        )
        logger.info(
            "Comentario procesado en dry-run -> comment_id=%s classification=%s",
            event.comment_id,
            decision.classification,
        )
        return

    try:
        _responder_comentario_publico(event.comment_id, decision.response_text)
        marcar_comment_estado(
            event.comment_id,
            "published",
            classification=decision.classification,
            response_text=decision.response_text,
        )
        logger.info(
            "Comentario respondido publicamente -> comment_id=%s classification=%s",
            event.comment_id,
            decision.classification,
        )
    except Exception as exc:
        error = _graph_error_resumen(exc)
        marcar_comment_estado(
            event.comment_id,
            "error",
            classification=decision.classification,
            response_text=decision.response_text,
            error=error,
        )
        logger.error("Error respondiendo comentario %s: %s", event.comment_id, error)


def procesar_comentarios_webhook(body: dict[str, Any], async_mode: bool = True) -> int:
    """Process comment events found in a webhook body.

    Returns the number of comment events detected.
    """
    count = 0
    for event in iter_comment_events(body):
        count += 1
        if async_mode:
            threading.Thread(
                target=procesar_comment_event,
                args=(event,),
                daemon=True,
            ).start()
        else:
            procesar_comment_event(event)
    return count
