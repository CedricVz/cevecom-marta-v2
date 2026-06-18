from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests

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

from config import cfg
from tools import instagram_comments as comments


class InstagramCommentsTests(unittest.TestCase):
    def _run_event(
        self,
        text: str,
        *,
        comment_id: str = "comment_1",
        author_id: str = "user_1",
        registrar_return: bool = True,
        enabled: str = "false",
        dry_run: str | None = "false",
        responder_side_effect=None,
    ):
        marks = []
        event = comments.InstagramCommentEvent(
            comment_id=comment_id,
            text=text,
            author_id=author_id,
            author_username="clienta",
            media_id="media_1",
        )

        def mark(*args, **kwargs):
            marks.append({"args": args, "kwargs": kwargs})

        env_patch = {"INSTAGRAM_COMMENTS_ENABLED": enabled}
        if dry_run is not None:
            env_patch["INSTAGRAM_COMMENTS_DRY_RUN"] = dry_run

        with patch.dict(os.environ, env_patch, clear=False):
            if dry_run is None:
                os.environ.pop("INSTAGRAM_COMMENTS_DRY_RUN", None)

            with patch.object(
                comments, "registrar_comment_recibido", return_value=registrar_return
            ) as registrar, patch.object(
                comments, "marcar_comment_estado", side_effect=mark
            ), patch.object(
                comments,
                "_responder_comentario_publico",
                side_effect=responder_side_effect,
            ) as responder:
                comments.procesar_comment_event(event)

        return registrar, responder, marks

    def test_dry_run_ausente_activa_modo_seguro(self):
        _registrar, responder, marks = self._run_event(
            "Me encanta el resultado",
            enabled="true",
            dry_run=None,
        )

        responder.assert_not_called()
        self.assertEqual(marks[0]["args"][1], "dry_run")
        self.assertEqual(marks[0]["kwargs"]["classification"], "felicitacion")

    def test_comentario_positivo(self):
        _registrar, responder, marks = self._run_event("Me encanta el resultado")

        responder.assert_not_called()
        self.assertEqual(marks[0]["args"][1], "dry_run")
        self.assertEqual(marks[0]["kwargs"]["classification"], "felicitacion")
        self.assertIn("guste", marks[0]["kwargs"]["response_text"])

    def test_pregunta_general(self):
        _registrar, responder, marks = self._run_event("Que es el HIFU?")

        responder.assert_not_called()
        self.assertEqual(marks[0]["args"][1], "dry_run")
        self.assertEqual(marks[0]["kwargs"]["classification"], "consulta_general")
        self.assertEqual(
            marks[0]["kwargs"]["response_text"],
            "Gracias por escribirnos. Para orientarte correctamente, "
            "puedes escribirnos por WhatsApp al 656 376 435.",
        )

    def test_intencion_reserva(self):
        _registrar, responder, marks = self._run_event("Quiero pedir cita para HIFU")

        responder.assert_not_called()
        self.assertEqual(marks[0]["args"][1], "dry_run")
        self.assertEqual(marks[0]["kwargs"]["classification"], "reserva")
        self.assertEqual(
            marks[0]["kwargs"]["response_text"],
            "Para reservar cita, escríbenos por WhatsApp al 656 376 435 "
            "y Marta o el equipo te ayudan directamente.",
        )

    def test_queja_no_responde(self):
        _registrar, responder, marks = self._run_event("Fatal, quiero poner una queja")

        responder.assert_not_called()
        self.assertEqual(marks[0]["args"][1], "needs_review")
        self.assertEqual(marks[0]["kwargs"]["classification"], "queja_reclamacion")

    def test_medico_sensible_no_responde(self):
        _registrar, responder, marks = self._run_event("Me ha dado alergia y me duele")

        responder.assert_not_called()
        self.assertEqual(marks[0]["args"][1], "needs_review")
        self.assertEqual(marks[0]["kwargs"]["classification"], "medico_sensible")

    def test_spam_no_responde(self):
        _registrar, responder, marks = self._run_event("Gana seguidores http://spam.test")

        responder.assert_not_called()
        self.assertEqual(marks[0]["args"][1], "ignored")
        self.assertEqual(marks[0]["kwargs"]["classification"], "spam")

    def test_evento_duplicado_no_responde(self):
        registrar, responder, marks = self._run_event(
            "Me encanta", registrar_return=False
        )

        registrar.assert_called_once()
        responder.assert_not_called()
        self.assertEqual(marks, [])

    def test_comentario_propia_cuenta(self):
        _registrar, responder, marks = self._run_event(
            "Gracias", author_id=cfg.instagram_user_id
        )

        responder.assert_not_called()
        self.assertEqual(marks[0]["args"][1], "ignored_own_account")

    def test_error_graph_api_queda_registrado(self):
        response = requests.Response()
        response.status_code = 500
        error = requests.HTTPError(response=response)

        _registrar, responder, marks = self._run_event(
            "Me encanta el resultado",
            enabled="true",
            dry_run="false",
            responder_side_effect=error,
        )

        responder.assert_called_once()
        self.assertEqual(marks[0]["args"][1], "error")
        self.assertEqual(marks[0]["kwargs"]["classification"], "felicitacion")
        self.assertIn("HTTP 500", marks[0]["kwargs"]["error"])

    def test_dm_webhook_sigue_enrutando_messaging(self):
        from tools import dm_responder

        payload = {
            "entry": [
                {
                    "messaging": [
                        {
                            "sender": {"id": "client_1"},
                            "message": {"text": "Hola, que tratamientos teneis?"},
                        }
                    ]
                }
            ]
        }

        with patch.object(dm_responder, "_procesar_dm") as procesar_dm, patch.object(
            dm_responder, "procesar_comentarios_webhook", return_value=0
        ), patch.object(dm_responder.threading, "Thread") as thread_cls:
            client = dm_responder.app.test_client()
            response = client.post("/webhook", json=payload)

        self.assertEqual(response.status_code, 200)
        thread_cls.assert_called_once()
        self.assertIs(thread_cls.call_args.kwargs["target"], procesar_dm)
        self.assertEqual(
            thread_cls.call_args.kwargs["args"],
            ("client_1", "Hola, que tratamientos teneis?"),
        )

    def test_payload_comments_extrae_identificadores(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "field": "comments",
                            "value": {
                                "id": "comment_123",
                                "text": "Gracias",
                                "from": {"id": "user_123", "username": "marta_fan"},
                                "media": {"id": "media_123"},
                            },
                        }
                    ]
                }
            ]
        }

        events = list(comments.iter_comment_events(payload))

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].comment_id, "comment_123")
        self.assertEqual(events[0].author_id, "user_123")
        self.assertEqual(events[0].author_username, "marta_fan")
        self.assertEqual(events[0].media_id, "media_123")

    def test_entry_malformado_se_ignora(self):
        payloads = [
            {},
            {"entry": None},
            {"entry": {"changes": []}},
            {"entry": ["no_es_objeto"]},
        ]

        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual(list(comments.iter_comment_events(payload)), [])

    def test_changes_malformado_se_ignora(self):
        payloads = [
            {"entry": [{"changes": None}]},
            {"entry": [{"changes": {"field": "comments"}}]},
            {"entry": [{"changes": ["no_es_objeto"]}]},
            {"entry": [{"changes": [{"field": "comments", "value": None}]}]},
            {"entry": [{"changes": [{"field": "comments", "value": "x"}]}]},
            {"entry": [{"changes": [{"field": "comments", "value": {"id": "c1"}}]}]},
            {"entry": [{"changes": [{"field": "comments", "value": {"text": "hola"}}]}]},
        ]

        for payload in payloads:
            with self.subTest(payload=payload):
                self.assertEqual(list(comments.iter_comment_events(payload)), [])

    def test_evento_desconocido_se_ignora(self):
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "field": "mentions",
                            "value": {"id": "comment_123", "text": "Gracias"},
                        }
                    ]
                }
            ]
        }

        self.assertEqual(list(comments.iter_comment_events(payload)), [])

    def test_webhook_devuelve_200_con_payload_malformado(self):
        from tools import dm_responder

        malformed_payloads = [
            [],
            {"entry": {"messaging": []}},
            {"entry": [{"messaging": {"sender": {"id": "x"}}}]},
            {"entry": [{"messaging": [None]}]},
            {"entry": [{"changes": {"field": "comments"}}]},
        ]

        client = dm_responder.app.test_client()
        with patch.object(dm_responder, "_procesar_dm") as procesar_dm, patch.object(
            dm_responder,
            "procesar_comentarios_webhook",
            wraps=dm_responder.procesar_comentarios_webhook,
        ):
            for payload in malformed_payloads:
                with self.subTest(payload=payload):
                    response = client.post("/webhook", json=payload)
                    self.assertEqual(response.status_code, 200)

        procesar_dm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
