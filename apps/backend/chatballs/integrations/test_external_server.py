"""Интеграция «Внешний сервер»: MCP-сервер и HTTP-запрос (SPEC-0023 R-1–R-4).

Настройки проверяются при сохранении, ошибки приходят фразами словаря и по
полям — все сразу, как их показывает форма.
"""

from __future__ import annotations

from chatballs.channels.models import Channel
from chatballs.i18n import t
from chatballs.integrations.external_server_testing import (
    TOKEN,
    URL,
    ExternalServerTestCase,
    order_status,
)
from chatballs.integrations.models import (
    Integration,
    IntegrationKind,
    IntegrationProvider,
    IntegrationStatus,
)
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.testing import system_tenant_context


class HttpRequestTests(ExternalServerTestCase):
    def test_http_request_is_stored_as_one_tool(self) -> None:
        response = self._create("HTTP", order_status())

        self.assertEqual(response.status_code, 201, response.content)
        payload = response.json()["integration"]
        self.assertEqual((payload["kind"], payload["provider"]), ("EXTERNAL_SERVER", "HTTP"))
        self.assertEqual(payload["status"], IntegrationStatus.UNCHECKED)
        self.assertTrue(payload["isActive"])
        server = payload["externalServer"]
        self.assertEqual(server["type"], "http")
        self.assertEqual(server["toolName"], "get_order_status")
        self.assertEqual(server["description"], "Статус заказа по номеру")
        self.assertEqual(server["method"], "GET")
        self.assertFalse(server["readOnly"])
        self.assertEqual(
            server["parameters"],
            [
                {
                    "name": "order_number",
                    "type": "string",
                    "description": "",
                    "required": True,  # параметр в адресе обязателен всегда
                    "location": "path",
                    "source": {"type": "ai"},
                },
                {
                    "name": "include_items",
                    "type": "boolean",
                    "description": "Нужен ли состав заказа",
                    "required": False,
                    "location": "query",
                    "source": {"type": "ai"},
                },
            ],
        )
        stored = Integration.objects.get(id=payload["id"])
        self.assertEqual(stored.kind, IntegrationKind.EXTERNAL_SERVER)

    def test_external_server_is_listed_with_other_integrations(self) -> None:
        created = self._create("HTTP", order_status()).json()["integration"]

        items = self.client.get(URL).json()["items"]

        self.assertIn(created["id"], [item["id"] for item in items])

    def test_tool_name_follows_the_pattern(self) -> None:
        for name in ("Get Order", "1order", "get-order", "", "a" * 41, "заказ"):
            with self.subTest(name=name):
                errors = self._errors(self._create("HTTP", order_status(toolName=name)))
                self.assertEqual(errors, {"toolName": [t("integrations.tool_name_invalid")]})
        for name in ("a", "get_order_2", "a" * 40):
            with self.subTest(name=name):
                response = self._create("HTTP", order_status(toolName=name), name=f"Запрос {name}")
                self.assertEqual(response.status_code, 201, response.content)

    def test_placeholder_without_parameter_is_refused(self) -> None:
        errors = self._errors(
            self._create("HTTP", order_status(url="https://shop.example.test/api/orders/{order_id}"))
        )

        self.assertIn(t("integrations.tool_url_placeholder_unknown", name="order_id"), errors["url"])
        self.assertIn("{order_id}", errors["url"][0])
        # Параметр «в адресе», которого в адресе нет.
        self.assertEqual(
            errors["parameters"], [t("integrations.tool_parameter_not_in_url", name="order_number")]
        )

    def test_local_network_address_is_refused(self) -> None:
        for url in (
            "http://192.168.1.20/api/orders/{order_number}",
            "http://postgres:5432/{order_number}",
            "http://127.0.0.1/{order_number}",
        ):
            with self.subTest(url=url):
                errors = self._errors(self._create("HTTP", order_status(url=url)))
                self.assertEqual(errors, {"url": [t("integrations.tool_address_local")]})

    def test_private_address_is_accepted_only_when_the_installation_allows_it(self) -> None:
        self._allow_private_network()

        allowed = self._create("HTTP", order_status(url="http://192.168.1.20/api/orders/{order_number}"))
        service = self._create("HTTP", order_status(url="http://postgres:5432/{order_number}"), name="Б")

        self.assertEqual(allowed.status_code, 201, allowed.content)
        self.assertEqual(self._errors(service), {"url": [t("integrations.tool_address_local")]})

    def test_all_errors_of_the_form_come_at_once(self) -> None:
        response = self._create(
            "HTTP",
            order_status(
                toolName="Get Order",
                method="POST",
                url="http://192.168.1.20/api/orders/{order_id}",
                parameters=[],
            ),
        )

        errors = self._errors(response)
        self.assertEqual(errors["toolName"], [t("integrations.tool_name_invalid")])
        self.assertEqual(
            errors["url"],
            [
                t("integrations.tool_url_placeholder_unknown", name="order_id"),
                t("integrations.tool_address_local"),
            ],
        )
        self.assertFalse(Integration.objects.filter(provider=IntegrationProvider.HTTP).exists())

    def test_host_cannot_be_a_placeholder(self) -> None:
        settings = order_status(
            url="https://{host}/api",
            parameters=[{"name": "host", "type": "string", "location": "path"}],
        )

        self.assertEqual(
            self._errors(self._create("HTTP", settings)),
            {"url": [t("integrations.tool_address_unresolved")]},
        )

    def test_read_only_mark_belongs_to_post(self) -> None:
        body = {"name": "query", "type": "string", "location": "body", "required": True}
        url = "https://shop.example.test/api/search"
        post = self._create("HTTP", order_status(method="POST", url=url, parameters=[body], readOnly=True))
        get = self._create("HTTP", order_status(url=url, parameters=[], readOnly=True), name="GET")
        body_in_get = self._create("HTTP", order_status(url=url, parameters=[body]), name="Тело")

        self.assertTrue(post.json()["integration"]["externalServer"]["readOnly"])
        self.assertFalse(get.json()["integration"]["externalServer"]["readOnly"])
        self.assertEqual(
            self._errors(body_in_get),
            {"parameters": [t("integrations.tool_parameter_body_post_only", name="query")]},
        )

    def test_parameter_is_bound_to_client_data(self) -> None:
        channel = Channel.objects.create(organization=self.organization, code="site", name="Сайт")
        web = create_integration(
            context=system_tenant_context(self.organization),
            data=IntegrationInput(
                provider=IntegrationProvider.WEB,
                name="Сайт",
                channel_id=channel.id,
                config={
                    "allowedOrigins": ["shop.example.test"],
                    "fields": [{"key": "order_number", "label": "Номер заказа", "type": "string"}],
                },
            ),
        )
        field = {"type": "web_field", "integrationId": web.id, "key": "order_number"}
        parameters = [
            {"name": "order_number", "type": "string", "location": "path", "source": field},
            {"name": "phone", "type": "string", "source": {"type": "contact", "field": "phone"}},
        ]

        created = self._create("HTTP", order_status(parameters=parameters))
        missing = self._create(
            "HTTP",
            order_status(parameters=[{**parameters[0], "source": {**field, "key": "unknown"}}]),
            name="Нет поля",
        )

        self.assertEqual(created.status_code, 201, created.content)
        sources = [item["source"] for item in created.json()["integration"]["externalServer"]["parameters"]]
        self.assertEqual(sources, [field, {"type": "contact", "field": "phone"}])
        self.assertEqual(
            self._errors(missing),
            {"parameters": [t("integrations.tool_parameter_field_not_found", name="order_number")]},
        )


class McpServerTests(ExternalServerTestCase):
    def _mcp(self, **overrides: object) -> dict:
        return {
            "description": "Заказы и цены",
            "url": "https://mcp.example.test/mcp",
            "headers": [{"name": "Authorization", "secret": True, "value": TOKEN}],
            **overrides,
        }

    def test_mcp_server_is_stored(self) -> None:
        response = self._create("MCP", self._mcp(), name="Магазин")

        self.assertEqual(response.status_code, 201, response.content)
        payload = response.json()["integration"]
        self.assertEqual((payload["kind"], payload["provider"]), ("EXTERNAL_SERVER", "MCP"))
        self.assertEqual(
            payload["externalServer"],
            {
                "type": "mcp",
                "description": "Заказы и цены",
                "url": "https://mcp.example.test/mcp",
                "headers": [{"name": "Authorization", "secret": True, "value": ""}],
                "tools": [],
                "toolsRefreshedAt": None,
                "toolsState": "not_loaded",
            },
        )

    def test_plain_http_needs_the_private_network_setting(self) -> None:
        refused = self._create("MCP", self._mcp(url="http://mcp.example.test/mcp"), name="А")
        local = self._create("MCP", self._mcp(url="https://192.168.1.20/mcp"), name="Б")
        self._allow_private_network()
        allowed = self._create("MCP", self._mcp(url="http://192.168.1.20/mcp"), name="В")

        self.assertEqual(
            self._errors(refused), {"url": [t("settings.url_scheme_required", schemes="https://")]}
        )
        self.assertEqual(self._errors(local), {"url": [t("integrations.tool_address_local")]})
        self.assertEqual(allowed.status_code, 201, allowed.content)

    def test_settings_are_required(self) -> None:
        response = self.client.post(URL, {"provider": "MCP", "name": "Магазин"}, format="json")

        self.assertEqual(self._errors(response), {"externalServer": [t("api.object_required")]})
