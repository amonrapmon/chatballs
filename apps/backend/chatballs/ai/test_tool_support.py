"""Признак «модель вызывает инструменты»: кеш и карточка агента (SPEC-0023 R-10)."""

from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from chatballs.ai import tool_support
from chatballs.ai.agent_card import agent_card_payload
from chatballs.ai.provider.base import ProviderError
from chatballs.ai.provider.custom import CustomProvider
from chatballs.ai.provider.openrouter import OpenRouterProvider
from chatballs.ai.tests import make_channel_with_agent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.testing import system_tenant_context

LOCAL_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=LOCAL_CACHE, CHATBALLS_AI_PROVIDER="")
class ToolSupportCacheTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        bootstrap_owner(email="owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.context = system_tenant_context(self.organization)
        self.channel, self.agent = make_channel_with_agent(
            self.organization, code="tool-support", name="Tool support", model=""
        )

    def _link(self, provider: str, *, model: str = "vendor/model"):
        base_url = (
            "https://api.example.com/v1"
            if provider == IntegrationProvider.CUSTOM
            else "https://openrouter.ai/api/v1"
        )
        integration = create_integration(
            context=self.context,
            data=IntegrationInput(
                provider=provider,
                name=f"BYOK {provider}",
                secret="sk-byok",
                config={"baseUrl": base_url, "defaultModel": model},
            ),
        )
        self.agent.provider_integration = integration
        self.agent.save(update_fields=["provider_integration"])
        return integration

    def test_agent_without_provider_is_unknown(self) -> None:
        self.assertIsNone(tool_support.resolve_tool_support(self.agent))
        self.assertIsNone(tool_support.cached_tool_support(self.agent))

    def test_openrouter_answer_is_cached(self) -> None:
        self._link(IntegrationProvider.OPENROUTER)
        with mock.patch.object(OpenRouterProvider, "supports_tools", return_value=True) as check:
            self.assertIsNone(tool_support.cached_tool_support(self.agent))
            self.assertTrue(tool_support.resolve_tool_support(self.agent))
            self.assertTrue(tool_support.resolve_tool_support(self.agent))
            self.assertTrue(tool_support.cached_tool_support(self.agent))
        check.assert_called_once_with(model="vendor/model")

    def test_custom_endpoint_is_probed_once(self) -> None:
        self._link(IntegrationProvider.CUSTOM)
        with mock.patch.object(CustomProvider, "supports_tools", return_value=False) as check:
            self.assertIs(tool_support.resolve_tool_support(self.agent), False)
            self.assertIs(tool_support.resolve_tool_support(self.agent), False)
        check.assert_called_once_with(model="vendor/model")

    def test_agent_model_overrides_integration_model(self) -> None:
        self._link(IntegrationProvider.OPENROUTER)
        self.agent.model = "vendor/agent-model"
        self.agent.save(update_fields=["model"])
        with mock.patch.object(OpenRouterProvider, "supports_tools", return_value=True) as check:
            tool_support.resolve_tool_support(self.agent)
        check.assert_called_once_with(model="vendor/agent-model")

    def test_answer_is_cached_per_model_and_integration_revision(self) -> None:
        integration = self._link(IntegrationProvider.OPENROUTER)
        with mock.patch.object(OpenRouterProvider, "supports_tools", return_value=True) as check:
            tool_support.resolve_tool_support(self.agent)
            self.agent.model = "vendor/other"
            tool_support.resolve_tool_support(self.agent)
            integration.runtime_revision += 1
            tool_support.resolve_tool_support(self.agent)
        self.assertEqual(check.call_count, 3)

    def test_provider_failure_is_unknown_and_not_repeated_at_once(self) -> None:
        self._link(IntegrationProvider.OPENROUTER)
        with mock.patch.object(
            OpenRouterProvider, "supports_tools", side_effect=ProviderError("down")
        ) as check:
            self.assertIsNone(tool_support.resolve_tool_support(self.agent))
            self.assertIsNone(tool_support.resolve_tool_support(self.agent))
        check.assert_called_once()

    def test_demo_provider_supports_tools_without_network(self) -> None:
        self._link(IntegrationProvider.DEMO, model="demo")
        with mock.patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            self.assertTrue(tool_support.resolve_tool_support(self.agent))

    def test_agent_card_returns_the_flag(self) -> None:
        self._link(IntegrationProvider.OPENROUTER)
        self.channel.refresh_from_db()
        with mock.patch.object(OpenRouterProvider, "supports_tools", return_value=True) as check:
            # Список агентов в сеть не ходит: до проверки признак неизвестен.
            self.assertIsNone(agent_card_payload(self.channel)["modelSupportsTools"])
            check.assert_not_called()
            card = agent_card_payload(self.channel, check_tool_support=True)
            self.assertIs(card["modelSupportsTools"], True)
            self.assertIs(agent_card_payload(self.channel)["modelSupportsTools"], True)
        check.assert_called_once()
