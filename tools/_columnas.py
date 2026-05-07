"""
Fuente de verdad para los nombres y orden de columnas de Google Sheets.
Sin dependencias — importable en cualquier contexto.
"""

CABECERAS: list[str] = [
    # ── Bloque 1: Briefing (rellena Marta) ────────────────────────────
    "Tema",
    "Tratamiento",
    "Audiencia",
    "Tono",
    "Look_ID",
    "Fecha_deseada",
    # ── Bloque 2: Producción (sistema) ────────────────────────────────
    # v1/v2: generar_guion.py escribe Estado y Guion
    # v3: leer_calendario_drive.py escribe Estado="Generando vídeo" y copia Guion de Marta
    "Estado",
    "Guion",
    "Video_preview",
    "Video_final",
    # ── Bloque 3: Aprobación ──────────────────────────────────────────
    "Email_enviado",
    "Decision",
    "Motivo_rechazo",
    # ── Bloque 4: Publicación ─────────────────────────────────────────
    "Fecha_publicacion",
    "URL_instagram",
    # ── Bloque 5: Técnico (no visible para Marta) ─────────────────────
    "Token_aprobacion",
    "ID_heygen",
    "Errores",
    "Reintentos",
]

# Índice por nombre → número de columna en Sheets (base 1), para updates directos
COL: dict[str, int] = {nombre: i + 1 for i, nombre in enumerate(CABECERAS)}
