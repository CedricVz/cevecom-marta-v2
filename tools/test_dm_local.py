"""Prueba local del agente de DMs sin enviar mensajes a Instagram.

Ejecuta el bypass determinista de reservas y, para mensajes informativos,
llama a OpenAI Responses API + file_search con el mismo prompt del agente.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.dm_responder import RESPUESTA_RESERVAS, _llamar_openai, _mensaje_es_reserva

DEFAULT_MESSAGES = [
    "¿El botox capilar elimina el frizz?",
    "¿El botox capilar quita el encrespado?",
    "¿Es como un alisado definitivo?",
    "Quiero hacerme botox capilar, ¿me das cita?",
]

PROHIBITED_PATTERNS = [
    r"elimina\s+(completamente|por completo)",
    r"elimina\s+el\s+frizz",
    r"elimina\s+el\s+encrespado",
    r"quita\s+el\s+encrespado",
    r"alisado\s+definitivo",
    r"resultado\s+permanente",
    r"garantizad",
    r"sin\s+frizz",
    r"adios\s+al\s+frizz",
    r"adiós\s+al\s+frizz",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prueba local del agente de DMs.")
    parser.add_argument(
        "--message",
        action="append",
        dest="messages",
        help="Mensaje a probar. Puede repetirse. Si se omite, usa casos por defecto.",
    )
    parser.add_argument("--json", action="store_true", help="Salida JSON.")
    return parser.parse_args()


def forbidden_matches(text: str) -> list[str]:
    normalized = "".join(
        c for c in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(c) != "Mn"
    )
    matches = []
    for pattern in PROHIBITED_PATTERNS:
        normalized_pattern = "".join(
            c for c in unicodedata.normalize("NFD", pattern.lower())
            if unicodedata.category(c) != "Mn"
        )
        for match in re.finditer(normalized_pattern, normalized):
            prefix = normalized[max(0, match.start() - 80):match.start()]
            if re.search(r"\b(no|ni|nunca)\b[^.!?\n]{0,80}$", prefix):
                continue
            matches.append(pattern)
            break
    return matches


def main() -> None:
    args = parse_args()
    messages = args.messages or DEFAULT_MESSAGES
    results = []

    for message in messages:
        is_reservation = _mensaje_es_reserva(message)
        if is_reservation:
            response = RESPUESTA_RESERVAS
            openai_called = False
        else:
            response, _response_id = _llamar_openai(message, prev_response_id=None)
            openai_called = True

        matches = forbidden_matches(response)
        result = {
            "message": message,
            "reservation_detected": is_reservation,
            "openai_called": openai_called,
            "response": response,
            "forbidden_matches": matches,
            "passed": not matches and (
                response == RESPUESTA_RESERVAS if is_reservation else True
            ),
        }
        results.append(result)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    for result in results:
        print("=" * 80)
        print(f"Mensaje: {result['message']}")
        print(f"Reserva detectada: {result['reservation_detected']}")
        print(f"Llamada OpenAI: {result['openai_called']}")
        print(f"Prohibidos detectados: {', '.join(result['forbidden_matches']) or 'ninguno'}")
        print(f"Veredicto automático: {'OK' if result['passed'] else 'REVISAR'}")
        print("Respuesta:")
        print(result["response"])


if __name__ == "__main__":
    main()
