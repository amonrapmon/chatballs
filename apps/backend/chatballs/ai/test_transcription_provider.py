"""Расшифровка голосовых может идти не к тому провайдеру, который отвечает.

Модель ответов часто не умеет речь в текст: у Anthropic и Yandex Foundation
Models эндпоинта `/audio/transcriptions` нет вовсе. Поэтому интеграция для
расшифровки выбирается на агенте отдельно.
"""

import json
import urllib.error
from io import BytesIO
from unittest import mock

from django.test import TestCase

from chatballs.ai.provider.base import ProviderError
from chatballs.ai.provider.custom import CustomProvider
from chatballs.ai.provider.routing import (
    resolve_transcription_model,
    resolve_transcription_provider,
)
from chatballs.ai.tests import make_channel_with_agent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.testing import system_tenant_context


class TranscriptionRoutingTests(TestCase):
    def setUp(self) -> None:
        bootstrap_owner(email="owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.context = system_tenant_context(self.organization)
        self.channel, self.agent = make_channel_with_agent(
            self.organization, code="voice-agent", name="Голосовой агент"
        )

    def _integration(self, *, name: str, base_url: str, transcription_model: str = ""):
        config = {"baseUrl": base_url, "defaultModel": "answer-model"}
        if transcription_model:
            config["transcriptionModel"] = transcription_model
        return create_integration(
            context=self.context,
            data=IntegrationInput(
                provider=IntegrationProvider.CUSTOM,
                name=name,
                secret="sk-key",
                config=config,
            ),
        )

    def test_without_a_choice_transcription_goes_to_the_answering_provider(self) -> None:
        answering = self._integration(
            name="Ответы", base_url="https://answers.example.test/v1"
        )
        self.agent.provider_integration = answering
        self.agent.save(update_fields=["provider_integration"])
        self.channel.refresh_from_db()

        provider = resolve_transcription_provider(self.channel)
        self.assertIsInstance(provider, CustomProvider)
        self.assertEqual(provider.base_url, "https://answers.example.test/v1")

    def test_chosen_integration_takes_the_voice(self) -> None:
        answering = self._integration(
            name="Ответы", base_url="https://answers.example.test/v1"
        )
        whisper = self._integration(
            name="Whisper",
            base_url="https://whisper.example.test/v1",
            transcription_model="whisper-large-v3",
        )
        self.agent.provider_integration = answering
        self.agent.transcription_integration = whisper
        self.agent.save(
            update_fields=["provider_integration", "transcription_integration"]
        )
        self.channel.refresh_from_db()

        provider = resolve_transcription_provider(self.channel)
        self.assertEqual(provider.base_url, "https://whisper.example.test/v1")
        self.assertEqual(resolve_transcription_model(self.channel), "whisper-large-v3")

    def test_model_defaults_to_whisper_of_the_chosen_integration(self) -> None:
        answering = self._integration(
            name="Ответы",
            base_url="https://answers.example.test/v1",
            transcription_model="answer-side-model",
        )
        whisper = self._integration(
            name="Whisper", base_url="https://whisper.example.test/v1"
        )
        self.agent.provider_integration = answering
        self.agent.transcription_integration = whisper
        self.agent.save(
            update_fields=["provider_integration", "transcription_integration"]
        )
        self.channel.refresh_from_db()

        self.assertEqual(resolve_transcription_model(self.channel), "whisper-1")


class TranscriptionErrorTextTests(TestCase):
    """Оператору — фраза, провайдеру — журнал: сырого ответа API в ленте нет."""

    def _provider(self) -> CustomProvider:
        return CustomProvider(
            api_key="sk-key", base_url="https://api.example.test/v1", timeout=5
        )

    def _fail_with(self, code: int, body: bytes):
        error = urllib.error.HTTPError(
            "https://api.example.test/v1/audio/transcriptions",
            code,
            "error",
            {},
            BytesIO(body),
        )
        return mock.patch(
            "chatballs.integrations.proxy.build_opener",
            return_value=mock.Mock(open=mock.Mock(side_effect=error)),
        )

    def _transcribe(self):
        return self._provider().transcribe(
            audio=b"0" * 16, filename="voice.ogg", content_type="audio/ogg", model="m"
        )

    def test_denied_request_does_not_leak_the_provider_answer(self) -> None:
        body = json.dumps(
            {"error": {"message": "Subscription is not supported for service accounts"}}
        ).encode()
        with self._fail_with(403, body), self.assertRaises(ProviderError) as caught:
            self._transcribe()
        message = str(caught.exception)
        self.assertNotIn("Subscription", message)
        self.assertNotIn("403", message)
        self.assertIn("ключ", message)

    def test_missing_endpoint_tells_where_to_look(self) -> None:
        with self._fail_with(404, b"not found"), self.assertRaises(ProviderError) as caught:
            self._transcribe()
        self.assertIn("расшифров", str(caught.exception).lower())
