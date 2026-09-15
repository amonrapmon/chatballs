import json
import urllib.request
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import TestCase

from chatballs.i18n import tn
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.integrations import checks
from chatballs.integrations.models import (
    Integration,
    IntegrationKind,
    IntegrationProvider,
    IntegrationStatus,
)
from chatballs.integrations.serializers import integration_payload
from chatballs.integrations.services import (
    IntegrationInput,
    create_integration,
    update_integration,
)
from chatballs.integrations.services import (
    test_integration as run_integration_test,
)
from chatballs.testing import system_tenant_context


def _fake_response(status: int, body: dict):

    response = mock.MagicMock()

    response.status = status

    response.read.return_value = json.dumps(body).encode("utf-8")

    return response





class WebIntegrationCheckTests(TestCase):

    """«Проверить» для Web-виджета: внешнего API нет — валидируем привязку к

    каналу и самостоятельный widget entry point подключения."""



    def setUp(self) -> None:

        bootstrap_owner(email="owner@example.com", password="temporary-password")

        self.organization = Organization.objects.get(slug="demo")

        self.context = system_tenant_context(self.organization)

        from chatballs.channels.models import Channel



        self.channel = Channel.objects.create(organization=self.organization, code="acme", name="Acme — главный сайт")



    def _web(self, name: str, channel=None, origins=("example.com",)) -> Integration:

        return create_integration(

            context=self.context,

            data=IntegrationInput(

                provider=IntegrationProvider.WEB,

                name=name,

                channel_id=channel.id if channel else None,

                config={"allowedOrigins": list(origins)},

            ),

        )



    def test_web_without_channel_fails(self) -> None:

        integration = run_integration_test(

            context=self.context, integration=self._web("Виджет", channel=None)

        )

        self.assertEqual(integration.status, IntegrationStatus.ERROR)

        self.assertIn("не привязано к каналу", integration.last_error)



    def test_web_bound_to_channel_is_ok(self) -> None:

        integration = run_integration_test(

            context=self.context, integration=self._web("Виджет", channel=self.channel)

        )

        self.assertEqual(integration.status, IntegrationStatus.OK)

        self.assertEqual(integration.last_error, "")

        self.assertEqual(integration.web_chat_widget.status, "PUBLISHED")

        self.assertTrue(integration_payload(integration)["webChatWidget"]["publicKey"])



    def test_two_web_connections_on_one_channel_are_independent(self) -> None:

        first = run_integration_test(

            context=self.context,

            integration=self._web("A-виджет", channel=self.channel),

        )

        second = run_integration_test(

            context=self.context, integration=self._web("B-виджет", channel=self.channel)

        )

        self.assertEqual(first.status, IntegrationStatus.OK)

        self.assertEqual(second.status, IntegrationStatus.OK)

        self.assertNotEqual(

            first.web_chat_widget.public_key,

            second.web_chat_widget.public_key,

        )



    def test_web_without_allowed_origins_fails(self) -> None:

        """Пустой allowed_origins в проде запрещает все домены, и виджет молча

        показывает «Чат временно недоступен» — проверка обязана это ловить."""

        integration = run_integration_test(

            context=self.context,

            integration=self._web("Виджет", channel=self.channel, origins=()),

        )

        self.assertEqual(integration.status, IntegrationStatus.ERROR)

        self.assertIn("Не заданы разрешённые домены", integration.last_error)

        self.assertEqual(integration.web_chat_widget.status, "DRAFT")



    def test_allowed_origins_reach_the_widget(self) -> None:

        integration = run_integration_test(

            context=self.context,

            integration=self._web(

                "Виджет", channel=self.channel, origins=("example.com", "*.example.com")

            ),

        )

        self.assertEqual(integration.status, IntegrationStatus.OK)

        self.assertEqual(

            integration.web_chat_widget.allowed_origins, ["example.com", "*.example.com"]

        )

        self.assertEqual(

            integration_payload(integration)["config"]["allowedOrigins"],

            ["example.com", "*.example.com"],

        )



    def test_saving_connection_keeps_the_widget_published(self) -> None:

        """Регрессия: раздача виджета требует PUBLISHED + OK (webchat.views), а правка

        подключения не должна ни ронять чат на сайте до ручного «Проверить», ни

        обнулять домены — именно так виджеты уходили в «Чат временно недоступен»."""

        integration = self._web("Виджет", channel=self.channel)

        self.assertEqual(integration.status, IntegrationStatus.OK)

        self.assertEqual(integration.web_chat_widget.status, "PUBLISHED")



        renamed = update_integration(

            context=self.context,

            integration=integration,

            data=IntegrationInput(

                provider=IntegrationProvider.WEB,

                name="Виджет · переименован",

                channel_id=self.channel.id,

                config={"allowedOrigins": ["example.com"]},

            ),

        )

        self.assertEqual(renamed.status, IntegrationStatus.OK)

        self.assertEqual(renamed.web_chat_widget.status, "PUBLISHED")

        self.assertEqual(renamed.config["allowed_domains"], ["example.com"])

        self.assertEqual(renamed.web_chat_widget.allowed_origins, ["example.com"])



class ProxyConfigTests(TestCase):

    def setUp(self) -> None:

        bootstrap_owner(email="owner@example.com", password="temporary-password")

        self.organization = Organization.objects.get(slug="demo")

        self.context = system_tenant_context(self.organization)



    def test_proxy_url_is_persisted_in_config(self) -> None:

        integration = create_integration(

            context=self.context,

            data=IntegrationInput(

                provider=IntegrationProvider.OPENROUTER,

                name="OpenRouter",

                secret="sk-test",

                config={"baseUrl": "https://openrouter.ai/api/v1", "proxyUrl": "http://user:pass@host:8080"},

            ),

        )

        self.assertEqual(integration.config["proxy_url"], "http://user:pass@host:8080")



    def test_update_clears_proxy_when_empty(self) -> None:

        integration = create_integration(

            context=self.context,

            data=IntegrationInput(

                provider=IntegrationProvider.OPENROUTER,

                name="OpenRouter",

                secret="sk-test",

                config={"proxyUrl": "http://host:8080"},

            ),

        )

        updated = update_integration(

            context=self.context,

            integration=integration,

            data=IntegrationInput(provider=IntegrationProvider.OPENROUTER, name="OpenRouter", config={"proxyUrl": ""}),

        )

        self.assertNotIn("proxy_url", updated.config)



    def test_serializer_exposes_proxy_url(self) -> None:

        integration = create_integration(

            context=self.context,

            data=IntegrationInput(

                provider=IntegrationProvider.OPENROUTER,

                name="OpenRouter",

                secret="sk-test",

                config={"proxyUrl": "http://host:8080"},

            ),

        )

        self.assertEqual(integration_payload(integration)["config"]["proxyUrl"], "http://host:8080")





def _patched_opener(captured: dict, body: dict):

    def fake_build_opener(proxy_url):

        captured["proxy_url"] = proxy_url

        opener = mock.MagicMock()

        ctx = mock.MagicMock()

        ctx.__enter__.return_value = _fake_response(200, body)

        opener.open.return_value = ctx

        return opener



    return fake_build_opener





class CheckProxyTransportTests(TestCase):

    """check_* должны прокидывать proxy_url в единый opener (build_opener)."""



    def test_check_openrouter_uses_proxy(self) -> None:

        captured = {}

        with mock.patch("chatballs.integrations.checks.build_opener", side_effect=_patched_opener(captured, {"data": {"label": "ok"}})):

            ok, detail, meta = checks.check_openrouter(secret="sk-test", base_url="", proxy_url="http://proxy:8080")



        self.assertTrue(ok)

        self.assertEqual(captured["proxy_url"], "http://proxy:8080")



    def test_check_openrouter_without_proxy_passes_empty(self) -> None:

        captured = {}

        with mock.patch("chatballs.integrations.checks.build_opener", side_effect=_patched_opener(captured, {"data": {"label": "ok"}})):

            checks.check_openrouter(secret="sk-test", base_url="", proxy_url="")



        self.assertEqual(captured["proxy_url"], "")



    def test_check_openrouter_supports_socks_url(self) -> None:

        captured = {}

        with mock.patch("chatballs.integrations.checks.build_opener", side_effect=_patched_opener(captured, {"data": {"label": "ok"}})):

            ok, detail, meta = checks.check_openrouter(secret="sk-test", base_url="", proxy_url="socks5://proxy:1080")



        self.assertTrue(ok)

        self.assertEqual(captured["proxy_url"], "socks5://proxy:1080")





class OutboundUserAgentTests(TestCase):

    """Продукт представляется своим именем: «Python-urllib» защита перед чужим
    API банит до самого API (на бою — Cloudflare «error code: 1010»)."""

    def test_opener_introduces_the_product(self) -> None:
        from chatballs.integrations.proxy import build_opener, user_agent

        for proxy in ("", "http://proxy:8080"):
            with self.subTest(proxy=proxy or "без прокси"):
                agents = dict(build_opener(proxy).addheaders)
                self.assertEqual(agents["User-Agent"], user_agent())
                self.assertNotIn("urllib", agents["User-Agent"])

    def test_request_keeps_its_own_agent(self) -> None:
        import urllib.request

        from chatballs.integrations.proxy import build_opener

        request = urllib.request.Request(
            "https://api.example.test/v1/models", headers={"User-Agent": "Mine/1.0"}
        )
        opener = build_opener("")
        # urllib добавляет заголовки opener'а только к тем, которых нет в запросе.
        self.assertEqual(request.get_header("User-agent"), "Mine/1.0")
        self.assertTrue(any(name == "User-Agent" for name, _ in opener.addheaders))


class CheckFailureTextTests(TestCase):

    """Отказ провайдера объясняется словами: голый код ничего не говорит."""

    def _reject(self, code: int, body: bytes):
        import urllib.error
        from io import BytesIO

        error = urllib.error.HTTPError(
            "https://api.example.test/v1/models", code, "Forbidden", {}, BytesIO(body)
        )
        return mock.patch(
            "chatballs.integrations.checks.build_opener",
            return_value=mock.Mock(open=mock.Mock(side_effect=error)),
        )

    def test_reason_from_the_provider_reaches_the_screen(self) -> None:
        body = json.dumps(
            {"error": {"message": "Your API key is invalid"}}
        ).encode()
        with self._reject(403, body):
            ok, detail, _meta = checks.check_custom(
                secret="sk-test", base_url="https://api.example.test/v1"
            )
        self.assertFalse(ok)
        self.assertIn("Your API key is invalid", detail)
        self.assertIn("403", detail)

    def test_html_block_page_is_squeezed_into_one_line(self) -> None:
        body = b"<html><head><title>Access denied</title></head><body><h1>Sorry, you have been blocked</h1></body></html>"
        with self._reject(403, body):
            ok, detail, _meta = checks.check_custom(
                secret="sk-test", base_url="https://api.example.test/v1"
            )
        self.assertFalse(ok)
        self.assertNotIn("<", detail)
        self.assertIn("blocked", detail.lower())

    def test_silent_refusal_tells_where_to_look(self) -> None:
        with self._reject(403, b""):
            ok, detail, _meta = checks.check_custom(
                secret="sk-test", base_url="https://api.example.test/v1"
            )
        self.assertFalse(ok)
        self.assertIn("регион", detail)


class OpenRouterProviderProxyTests(TestCase):

    def test_provider_routes_through_proxy_handler(self) -> None:

        from chatballs.ai.provider.openrouter import OpenRouterProvider



        captured = {}

        provider = OpenRouterProvider(api_key="sk-test", base_url="https://openrouter.ai/api/v1", proxy_url="http://proxy:8080")

        # После рефакторинга общий HTTP-слой живёт в openai_http (ADR-HUB-0033 §7):

        # мокаем именно его build_opener.

        with mock.patch("chatballs.ai.provider.openai_http.build_opener", side_effect=_patched_opener(captured, {"choices": [{"message": {"content": "ok"}}], "model": "x"})):

            result = provider.chat(messages=[], model="x")



        self.assertEqual(result.text, "ok")

        self.assertEqual(captured["proxy_url"], "http://proxy:8080")





class BuildOpenerSocksTests(TestCase):

    def test_http_scheme_uses_proxy_handler(self) -> None:

        from chatballs.integrations.proxy import build_opener



        opener = build_opener("http://proxy:8080")

        self.assertTrue(any(isinstance(h, urllib.request.ProxyHandler) for h in opener.handlers))



    def test_socks5_scheme_builds_socks_handler(self) -> None:

        from chatballs.integrations.proxy import build_opener



        opener = build_opener("socks5://user:pass@host:1080")

        # PySocks установлен → handler строится без ошибок и не является ProxyHandler.

        self.assertFalse(any(isinstance(h, urllib.request.ProxyHandler) for h in opener.handlers))



    def test_socks_without_pysocks_raises_value_error(self) -> None:

        from chatballs.integrations import proxy
        from chatballs.integrations.proxy import build_opener



        with mock.patch.object(proxy, "_import_socks", side_effect=ValueError("no PySocks")):

            with self.assertRaises(ValueError):

                build_opener("socks5://host:1080")





class CustomIntegrationTests(TestCase):

    """Generic OpenAI-compatible BYOK provider (ADR-CHATBALLS-0034, SPEC-CHATBALLS-0024 §5).



    Covers the three required fields (endpoint, API key, model), runtime

    reading of the model field (SPEC #2, #5 — closing the as-built gap where

    «Модель по умолчанию» was decorative), and the connectivity check against

    an arbitrary OpenAI-compatible endpoint.

    """



    def setUp(self) -> None:

        bootstrap_owner(email="owner@example.com", password="temporary-password")

        self.organization = Organization.objects.get(slug="demo")

        self.context = system_tenant_context(self.organization)



    def test_custom_persists_endpoint_and_model(self) -> None:

        integration = create_integration(

            context=self.context,

            data=IntegrationInput(

                provider=IntegrationProvider.CUSTOM,

                name="Мой провайдер",

                secret="sk-custom",

                config={

                    "baseUrl": "https://api.example.com/v1",

                    "defaultModel": "local-llama-3",

                },

            ),

        )

        # Модель — отдельное рабочее поле (ADR-CHATBALLS-0034 §4), читается в рантайме.

        self.assertEqual(integration.config["base_url"], "https://api.example.com/v1")

        self.assertEqual(integration.config["default_model"], "local-llama-3")

        self.assertEqual(integration.kind, IntegrationKind.LLM_PROVIDER)



    def test_custom_requires_model_free_text(self) -> None:

        with self.assertRaises(ValidationError):

            create_integration(

                context=self.context,

                data=IntegrationInput(

                    provider=IntegrationProvider.CUSTOM,

                    name="Мой провайдер",

                    secret="sk-custom",

                    config={"baseUrl": "https://api.example.com/v1"},

                ),

            )



    def test_custom_requires_base_url_and_api_key(self) -> None:

        with self.assertRaises(ValidationError):

            create_integration(

                context=self.context,

                data=IntegrationInput(

                    provider=IntegrationProvider.CUSTOM,

                    name="Без endpoint",

                    secret="sk-custom",

                    config={"defaultModel": "local-model"},

                ),

            )

        with self.assertRaises(ValidationError):

            create_integration(

                context=self.context,

                data=IntegrationInput(

                    provider=IntegrationProvider.CUSTOM,

                    name="Без ключа",

                    secret="",

                    config={

                        "baseUrl": "https://api.example.com/v1",

                        "defaultModel": "local-model",

                    },

                ),

            )



    def test_check_custom_lists_models_on_openai_shape(self) -> None:

        captured = {}

        with mock.patch("chatballs.integrations.checks.build_opener", side_effect=_patched_opener(captured, {"data": [{"id": "local-llama-3"}]})):

            ok, detail, meta = checks.check_custom(secret="sk-custom", base_url="https://api.example.com/v1")



        self.assertTrue(ok)

        self.assertEqual(detail, tn("integrations.check_endpoint_models", 1))



    def test_check_custom_without_secret_fails(self) -> None:

        ok, detail, meta = checks.check_custom(secret="", base_url="https://api.example.com/v1")

        self.assertFalse(ok)

        self.assertEqual(detail, "Не указан API-ключ")



    def test_check_custom_without_base_url_fails(self) -> None:

        ok, detail, meta = checks.check_custom(secret="sk-custom", base_url="")

        self.assertFalse(ok)

        self.assertEqual(detail, "Не указан Base URL")



    def test_check_custom_non_200_is_error(self) -> None:

        response = mock.MagicMock()

        response.status = 401

        response.read.return_value = b"{}"

        opener = mock.MagicMock()

        ctx = mock.MagicMock()

        ctx.__enter__.return_value = response

        opener.open.return_value = ctx

        with mock.patch("chatballs.integrations.checks.build_opener", return_value=opener):

            ok, detail, meta = checks.check_custom(secret="sk-custom", base_url="https://api.example.com/v1")



        self.assertFalse(ok)

        self.assertIn("401", detail)

