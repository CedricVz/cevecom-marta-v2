"""tools/migrar_sqlite_a_postgres.py — Migración one-shot del contexto de DMs.

Lee la tabla `contexto` de `dm_context.db` (SQLite local) y vuelca cada fila a
la tabla `dm_context` de PostgreSQL (Railway) con UPSERT, conservando el
response_id por usuario para que el contexto de OpenAI no se rompa al cambiar
de backend.

Uso (una sola vez, desde local):

    1. En `.env` define DATABASE_URL apuntando al DATABASE_PUBLIC_URL del
       servicio Postgres en Railway (Connect → Public Network).
    2. Asegúrate de que dm_context.db existe en la raíz del proyecto.
    3. python tools/migrar_sqlite_a_postgres.py

El script crea la tabla `dm_context` si no existe (mismo CREATE que
db_context.py). Es idempotente: ejecutarlo dos veces deja el mismo resultado.
"""

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import cfg  # noqa: F401  fuerza la validación de variables de entorno
from tools.db_context import _conn, _ensure_schema

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s", stream=sys.stderr)
logger = logging.getLogger("migrar_sqlite_a_postgres")

SQLITE_PATH = Path(__file__).parent.parent / "dm_context.db"


def main() -> None:
    if not SQLITE_PATH.exists():
        logger.error("No se encuentra %s — nada que migrar.", SQLITE_PATH)
        sys.exit(1)

    _ensure_schema()

    with sqlite3.connect(SQLITE_PATH) as src:
        rows = src.execute(
            "SELECT instagram_user_id, response_id, updated_at FROM contexto"
        ).fetchall()

    logger.info("Filas en SQLite: %d", len(rows))
    if not rows:
        logger.info("Nada que migrar.")
        return

    migradas = 0
    with _conn() as dst, dst.cursor() as cur:
        for instagram_user_id, response_id, updated_at in rows:
            cur.execute(
                """
                INSERT INTO dm_context (instagram_user_id, response_id, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (instagram_user_id) DO UPDATE SET
                    response_id = EXCLUDED.response_id,
                    updated_at  = EXCLUDED.updated_at
                """,
                (instagram_user_id, response_id, updated_at),
            )
            migradas += 1

    logger.info("Migradas %d/%d fila(s) a PostgreSQL.", migradas, len(rows))


if __name__ == "__main__":
    main()
