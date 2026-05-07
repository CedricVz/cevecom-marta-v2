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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dm_context (
    instagram_user_id TEXT PRIMARY KEY,
    response_id       TEXT NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
"""

_initialized = False


@contextmanager
def _conn() -> Iterator[PGConnection]:
    c = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        yield c
        c.commit()
    finally:
        c.close()


def _ensure_schema() -> None:
    global _initialized
    if _initialized:
        return
    with _conn() as c, c.cursor() as cur:
        cur.execute(_SCHEMA)
    _initialized = True


def leer_response_id(instagram_user_id: str) -> Optional[str]:
    _ensure_schema()
    with _conn() as c, c.cursor() as cur:
        cur.execute(
            "SELECT response_id FROM dm_context WHERE instagram_user_id = %s",
            (instagram_user_id,),
        )
        row = cur.fetchone()
    return row[0] if row else None


def guardar_response_id(instagram_user_id: str, response_id: str) -> None:
    _ensure_schema()
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
