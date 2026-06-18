from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import openai

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


REQUIRED_ENV = {
    "ANTHROPIC_API_KEY": "test",
    "HEYGEN_API_KEY": "test",
    "GOOGLE_SHEETS_ID": "test",
    "EMAIL_SMTP_USER": "test@example.com",
    "EMAIL_SMTP_PASSWORD": "test",
    "EMAIL_DESTINATARIO": "test@example.com",
    "EMAIL_COPIA_PRESTADOR": "test@example.com",
    "APPS_SCRIPT_WEBHOOK_URL": "https://example.com",
    "FACEBOOK_APP_ID": "123",
    "FACEBOOK_APP_SECRET": "secret",
    "FACEBOOK_PAGE_ID": "page_1",
    "INSTAGRAM_USER_ID": "ig_self",
    "FACEBOOK_ACCESS_TOKEN": "token",
    "OPENAI_API_KEY": "sk-test",
    "OPENAI_VECTOR_STORE_ID": "vs_test",
    "OPENAI_ASSISTANT_ID": "asst_test",
    "META_WEBHOOK_VERIFY_TOKEN": "verify",
    "INSTAGRAM_API_TOKEN": "token",
    "GOOGLE_CREDENTIALS_JSON": "{}",
}

for key, value in REQUIRED_ENV.items():
    os.environ.setdefault(key, value)

from tools import dm_responder


def _http_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.openai.test/v1/responses")
    return httpx.Response(status_code=status_code, request=request)


def _bad_request(body: dict, message: str = "Bad request") -> openai.BadRequestError:
    return openai.BadRequestError(message, response=_http_response(400), body=body)


def _previous_response_error() -> openai.BadRequestError:
    return _bad_request(
        {
            "type": "invalid_request_error",
            "param": "previous_response_id",
            "code": "invalid_previous_response_id",
            "message": "Previous response not found.",
        },
        message="Previous response not found.",
    )


def _rate_limit_error() -> openai.RateLimitError:
    return openai.RateLimitError(
        "Rate limit reached",
        response=_http_response(429),
        body={"type": "rate_limit_error", "param": None, "code": "rate_limit_exceeded"},
    )


def _server_error() -> openai.InternalServerError:
    return openai.InternalServerError(
        "Server error",
        response=_http_response(500),
        body={"type": "server_error", "param": None, "code": "server_error"},
    )


def _network_error() -> openai.APIConnectionError:
    request = httpx.Request("POST", "https://api.openai.test/v1/responses")
    return openai.APIConnectionError(message="Connection error.", request=request)


class DmPreviousResponseFallbackTests(unittest.TestCase):
    def _run_dm(self, previous_response_id, side_effect):
        with patch.object(dm_responder, "_mensaje_es_reserva", return_value=False), patch.object(
            dm_responder, "leer_response_id", return_value=previous_response_id
        ) as leer, patch.object(
            dm_responder, "_llamar_openai", side_effect=side_effect
        ) as llamar, patch.object(
            dm_responder, "guardar_response_id"
        ) as guardar, patch.object(
            dm_responder, "_enviar_dm"
        ) as enviar, patch.object(
            dm_responder, "_notificar_error"
        ) as notificar:
            dm_responder._procesar_dm("sender_123456", "Hola")

        return leer, llamar, guardar, enviar, notificar

    def test_sin_contexto_previo_una_llamada_sin_previous_response_id(self):
        _leer, llamar, guardar, enviar, notificar = self._run_dm(
            None,
            [("Respuesta nueva", "resp_new")],
        )

        self.assertEqual(llamar.call_count, 1)
        self.assertEqual(llamar.call_args_list[0].args, ("Hola", None))
        guardar.assert_called_once_with("sender_123456", "resp_new")
        enviar.assert_called_once_with("sender_123456", "Respuesta nueva")
        notificar.assert_not_called()

    def test_contexto_valido_una_llamada_con_previous_response_id(self):
        _leer, llamar, guardar, enviar, notificar = self._run_dm(
            "resp_old",
            [("Respuesta contextual", "resp_new")],
        )

        self.assertEqual(llamar.call_count, 1)
        self.assertEqual(llamar.call_args_list[0].args, ("Hola", "resp_old"))
        guardar.assert_called_once_with("sender_123456", "resp_new")
        enviar.assert_called_once_with("sender_123456", "Respuesta contextual")
        notificar.assert_not_called()

    def test_contexto_invalido_confirmado_reintenta_sin_previous_response_id(self):
        _leer, llamar, guardar, enviar, notificar = self._run_dm(
            "resp_old",
            [_previous_response_error(), ("Respuesta nueva", "resp_new")],
        )

        self.assertEqual(llamar.call_count, 2)
        self.assertEqual(llamar.call_args_list[0].args, ("Hola", "resp_old"))
        self.assertEqual(llamar.call_args_list[1].args, ("Hola", None))
        guardar.assert_called_once_with("sender_123456", "resp_new")
        enviar.assert_called_once_with("sender_123456", "Respuesta nueva")
        notificar.assert_not_called()

    def test_bad_request_no_relacionado_no_reintenta(self):
        error = _bad_request(
            {
                "type": "invalid_request_error",
                "param": "model",
                "code": "invalid_model",
                "message": "Model is invalid.",
            }
        )

        _leer, llamar, guardar, enviar, notificar = self._run_dm("resp_old", [error])

        self.assertEqual(llamar.call_count, 1)
        guardar.assert_not_called()
        enviar.assert_not_called()
        notificar.assert_called_once()

    def test_rate_limit_no_reintenta_sin_contexto(self):
        _leer, llamar, guardar, enviar, notificar = self._run_dm(
            "resp_old",
            [_rate_limit_error()],
        )

        self.assertEqual(llamar.call_count, 1)
        guardar.assert_not_called()
        enviar.assert_not_called()
        notificar.assert_called_once()

    def test_error_de_red_o_servidor_no_reintenta_sin_contexto(self):
        for error in (_network_error(), _server_error()):
            with self.subTest(error=type(error).__name__):
                _leer, llamar, guardar, enviar, notificar = self._run_dm(
                    "resp_old",
                    [error],
                )

                self.assertEqual(llamar.call_count, 1)
                guardar.assert_not_called()
                enviar.assert_not_called()
                notificar.assert_called_once()

    def test_si_falla_el_segundo_intento_no_guarda_ni_reintenta_tercera_vez(self):
        _leer, llamar, guardar, enviar, notificar = self._run_dm(
            "resp_old",
            [_previous_response_error(), RuntimeError("segundo intento falla")],
        )

        self.assertEqual(llamar.call_count, 2)
        self.assertEqual(llamar.call_args_list[0].args, ("Hola", "resp_old"))
        self.assertEqual(llamar.call_args_list[1].args, ("Hola", None))
        guardar.assert_not_called()
        enviar.assert_not_called()
        notificar.assert_called_once()


if __name__ == "__main__":
    unittest.main()
