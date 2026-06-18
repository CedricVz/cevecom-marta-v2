"""tools/db_context.py — Contexto de DMs en PostgreSQL (Railway).

Reemplaza la persistencia SQLite local. Lee DATABASE_URL de las variables de
entorno (Railway la inyecta automáticamente cuando hay un servicio Postgres
hermano en el mismo proyecto). Para uso local, copia DATABASE_PUBLIC_URL desde
el dashboard del Postgres de Railway al .env.

Crea la tabla `dm_context` la primera vez que se llama a una función de lectura
o escritura (idempotente vía CREATE TABLE IF NOT EXISTS).
"""

import os
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

import psycopg2
from psycopg2.extensions import connection as PGConnection

_DM_SCHEMA = """
CREATE TABLE IF NOT EXISTS dm_context (
    instagram_user_id TEXT PRIMARY KEY,
    response_id       TEXT NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

_COMMENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS instagram_comment_events (
    comment_id      TEXT PRIMARY KEY,
    media_id        TEXT,
    author_id       TEXT,
    author_username TEXT,
    comment_text    TEXT NOT NULL,
    classification  TEXT,
    status          TEXT NOT NULL,
    response_text   TEXT,
    error           TEXT,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

_dm_initialized = False
_comments_initialized = False


@contextmanager
def _conn() -> Iterator[PGConnection]:
    c = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        yield c
        c.commit()
    finally:
        c.close()


def _ensure_dm_schema() -> None:
    global _dm_initialized
    if _dm_initialized:
        return
    with _conn() as c, c.cursor() as cur:
        cur.execute(_DM_SCHEMA)
    _dm_initialized = True


def _ensure_comments_schema() -> None:
    global _comments_initialized
    if _comments_initialized:
        return
    with _conn() as c, c.cursor() as cur:
        cur.execute(_COMMENTS_SCHEMA)
    _comments_initialized = True


def leer_response_id(instagram_user_id: str) -> Optional[str]:
    _ensure_dm_schema()
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT response_id FROM dm_context WHERE instagram_user_id = %s",
            (instagram_user_id,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def guardar_response_id(instagram_user_id: str, response_id: str) -> None:
    _ensure_dm_schema()
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dm_context (instagram_user_id, response_id, updated_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (instagram_user_id) DO UPDATE SET
                response_id = EXCLUDED.response_id,
                updated_at  = EXCLUDED.updated_at
            """,
            (instagram_user_id, response_id, datetime.now(timezone.utc)),
        )


def registrar_comment_recibido(
    comment_id: str,
    media_id: Optional[str],
    author_id: Optional[str],
    author_username: Optional[str],
    comment_text: str,
) -> bool:
    """Registra un comentario nuevo. Devuelve False si ya existia."""
    _ensure_comments_schema()
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """
            INSERT INTO instagram_comment_events (
                comment_id, media_id, author_id, author_username,
                comment_text, status, first_seen_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (comment_id) DO NOTHING
            """,
            (
                comment_id,
                media_id,
                author_id,
                author_username,
                comment_text,
                "received",
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
            ),
        )
        return cur.rowcount == 1


def marcar_comment_estado(
    comment_id: str,
    status: str,
    classification: Optional[str] = None,
    response_text: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    _ensure_comments_schema()
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            """
            UPDATE instagram_comment_events
            SET status = %s,
                classification = COALESCE(%s, classification),
                response_text = COALESCE(%s, response_text),
                error = %s,
                updated_at = %s
            WHERE comment_id = %s
            """,
            (
                status,
                classification,
                response_text,
                error,
                datetime.now(timezone.utc),
                comment_id,
            ),
        )
