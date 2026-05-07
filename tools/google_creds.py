"""tools/google_creds.py — Helper para credenciales de Google Service Account.

Soporta dos modos:
  - LOCAL: lee `credentials.json` desde la ruta `cfg.google_credentials_path`.
  - RAILWAY (o cualquier servidor): lee el JSON completo desde la variable
    de entorno `GOOGLE_CREDENTIALS_JSON`. Esto evita subir el archivo al repo.

Si `GOOGLE_CREDENTIALS_JSON` está definida y no vacía, se usa esa. Si no,
fallback al archivo en disco.
"""

import json
import os
from typing import Sequence

from google.oauth2.service_account import Credentials

from config import cfg


def service_account_credentials(scopes: Sequence[str]) -> Credentials:
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON", "").strip()
    if raw:
        return Credentials.from_service_account_info(json.loads(raw), scopes=list(scopes))
    return Credentials.from_service_account_file(
        str(cfg.google_credentials_path), scopes=list(scopes)
    )
