"""Снимок инструментов MCP-сервера и проверка соединения (SPEC-0023 R-2, R-5)."""

from __future__ import annotations

from django.test import override_settings

from chatballs.i18n import t
from chatballs.identity.instance_settings import InstanceSettings
from chatballs.integrations.external_server_testing import (
    DNS,
    TOKEN,
    URL,
    ExternalServerTestCase,
    order_status,
)
from chatballs.integrations.external_tools import call_tool
from chatballs.integrations.mcp_testing import UPSTREAM_SECRET, FakeMcpServer
from chatballs.integrations.models import Integration
from chatballs.integrations.tool_testing import fake_dns

HEADERS = [{"name": "Authorization", "secret": True, "value": TOKEN}]


class McpToolsTestCase(ExternalServerTestCase):
    def setUp(self) -> None:
        super().setUp()
        fake_dns(self, {**DNS, "intranet.example.test": ["192.168.1.20"]})
        # Поддельный сервер отвечает по http, а его принимает только эта настройка.
        self._allow_private_network()
        self.server = FakeMcpServer()
        self.server.start(self)
        self.server.token = TOKEN

    def _server(self, host: str = "mcp.example.test") -> dict:
        response = self._create(
            "MCP", {"url": self.server.url(host), "headers": HEADERS}, name="Магазин"
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["integration"]

    def _post(self, integration: dict, action: str) -> dict:
        response = self.client.post(f"{URL}{integration['id']}/{action}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn(UPSTREAM_SECRET, response.content.decode())
        return response.json()["integration"]

    def _refresh(self, integration: dict) -> dict:
        return self._post(integration, "tools/refresh")


class ToolsSnapshotTests(McpToolsTestCase):
    def test_new_server_has_no_list_yet(self) -> None:
        external = self._server()["externalServer"]

        self.assertEqual(
            (external["tools"], external["toolsRefreshedAt"], external["toolsState"]),
            ([], None, "not_loaded"),
        )

    def test_refresh_stores_the_snapshot_and_the_time(self) -> None:
        refreshed = self._refresh(self._server())

        external = refreshed["externalServer"]
        self.assertEqual((refreshed["status"], external["toolsState"]), ("OK", "loaded"))
        self.assertEqual(
            external["tools"][0],
            {
                "name": "get_order_status",
                "title": "Статус заказа",
                "description": "Возвращает статус и время доставки заказа по номеру",
                "inputSchema": {
                    "type": "object",
                    "properties": {"order_number": {"type": "string"}},
                    "required": ["order_number"],
                },
                "readOnlyHint": True,
                "readOnlyConfirmation": None,
            },
        )
        self.assertEqual(
            (external["tools"][1]["name"], external["tools"][1]["readOnlyHint"]),
            ("cancel_order", False),
        )
        stored = Integration.objects.get(id=refreshed["id"])
        self.assertEqual(len(stored.tools), 2)
        self.assertEqual(stored.tools_refreshed_at.isoformat(), external["toolsRefreshedAt"])
        # Снимок переживает перечитывание списка интеграций.
        listed = next(
            item for item in self.client.get(URL).json()["items"] if item["id"] == refreshed["id"]
        )
        self.assertEqual(listed["externalServer"]["tools"], external["tools"])

    def test_failed_refresh_keeps_the_previous_snapshot(self) -> None:
        loaded = self._refresh(self._server())
        self.server.token = "Bearer rotated"

        failed = self._refresh(loaded)

        external = failed["externalServer"]
        self.assertEqual((failed["status"], external["toolsState"]), ("ERROR", "unauthorized"))
        self.assertEqual(failed["lastError"], t("integrations.server_unauthorized", host="mcp.example.test"))
        self.assertEqual(external["tools"], loaded["externalServer"]["tools"])
        self.assertEqual(external["toolsRefreshedAt"], loaded["externalServer"]["toolsRefreshedAt"])

        self.server.token = TOKEN
        self.assertEqual(self._refresh(failed)["externalServer"]["toolsState"], "loaded")

    @override_settings(CHATBALLS_AI_REQUEST_TIMEOUT=0.3)
    def test_timeout_is_an_unreachable_server_and_keeps_the_snapshot(self) -> None:
        loaded = self._refresh(self._server())
        self.server.delay = 1.5

        failed = self._refresh(loaded)

        self.assertEqual((failed["status"], failed["externalServer"]["toolsState"]), ("ERROR", "unreachable"))
        self.assertEqual(failed["lastError"], t("integrations.server_unreachable", host="mcp.example.test"))
        self.assertEqual(len(failed["externalServer"]["tools"]), 2)

    def test_server_without_tools(self) -> None:
        self.server.tools = []

        refreshed = self._refresh(self._server())

        external = refreshed["externalServer"]
        self.assertEqual((refreshed["status"], external["toolsState"]), ("OK", "no_tools"))
        self.assertEqual(external["tools"], [])
        self.assertIsNotNone(external["toolsRefreshedAt"])

    def test_malformed_tools_are_dropped(self) -> None:
        self.server.tools = [
            {"name": "get_prices", "description": 7, "inputSchema": "nope"},
            {"name": "get_prices"},
            {"name": ""},
            {"description": "без имени"},
        ]

        tools = self._refresh(self._server())["externalServer"]["tools"]

        self.assertEqual(
            tools,
            [
                {
                    "name": "get_prices",
                    "title": "",
                    "description": "",
                    "inputSchema": {"type": "object", "properties": {}},
                    "readOnlyHint": False,
                    "readOnlyConfirmation": None,
                }
            ],
        )

    def test_saving_settings_keeps_the_snapshot(self) -> None:
        loaded = self._refresh(self._server())

        response = self.client.patch(
            f"{URL}{loaded['id']}/",
            {"externalServer": {"url": self.server.url(), "headers": loaded["externalServer"]["headers"]}},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json()["integration"]["externalServer"]["tools"], loaded["externalServer"]["tools"]
        )

    def test_http_request_has_no_tool_list(self) -> None:
        created = self._create("HTTP", order_status()).json()["integration"]

        response = self.client.post(f"{URL}{created['id']}/tools/refresh/")

        self.assertEqual(response.status_code, 400, response.content)
        self.assertNotIn("tools", created["externalServer"])
        self.assertEqual(self.server.requests, [])

    def test_tool_call_uses_the_stored_headers(self) -> None:
        integration = Integration.objects.get(id=self._server()["id"])

        result = call_tool(integration, "get_order_status", {"order_number": "10482"}, timeout=5)

        self.assertEqual((result.text, result.is_error), ("Заказ в пути", False))
        self.assertEqual(self.server.requests[-2]["headers"]["authorization"], TOKEN)


class ConnectionCheckTests(McpToolsTestCase):
    def _check(self, integration: dict) -> dict:
        return self._post(integration, "test")

    def test_check_initializes_and_leaves_the_list_alone(self) -> None:
        checked = self._check(self._server())

        self.assertEqual((checked["status"], checked["lastError"]), ("OK", ""))
        self.assertEqual(checked["externalServer"]["toolsState"], "not_loaded")
        self.assertNotIn("tools/list", self.server.methods)
        self.assertIn("initialize", self.server.methods)

    def test_check_tells_the_states_apart(self) -> None:
        unauthorized = self._server()
        self.server.token = "Bearer rotated"
        forbidden = self._create(
            "MCP", {"url": self.server.url("intranet.example.test")}, name="Склад"
        ).json()["integration"]
        InstanceSettings.objects.update(tools_private_network=False)
        cases = (
            (unauthorized, "unauthorized", "mcp.example.test"),
            (forbidden, "address_forbidden", "intranet.example.test"),
        )
        for integration, state, host in cases:
            with self.subTest(state=state):
                checked = self._check(integration)
                self.assertEqual(checked["status"], "ERROR")
                self.assertEqual(checked["externalServer"]["toolsState"], state)
                self.assertEqual(checked["lastError"], t(f"integrations.server_{state}", host=host))
        # К запрещённому адресу соединения не было.
        self.assertNotIn("192.168.1.20", self.server.dialed)

    def test_answer_that_is_not_mcp_is_an_unreachable_server(self) -> None:
        self.server.html = True

        checked = self._check(self._server())

        self.assertEqual((checked["status"], checked["externalServer"]["toolsState"]), ("ERROR", "unreachable"))

    def test_saving_settings_clears_the_error(self) -> None:
        self.server.token = "Bearer rotated"
        failed = self._check(self._server())

        saved = self.client.patch(f"{URL}{failed['id']}/", {"name": "Магазин 2"}, format="json")

        integration = saved.json()["integration"]
        self.assertEqual((integration["status"], integration["lastError"]), ("UNCHECKED", ""))
        self.assertEqual(integration["externalServer"]["toolsState"], "not_loaded")

    def test_http_request_is_checked_without_a_call(self) -> None:
        created = self._create("HTTP", order_status()).json()["integration"]

        checked = self._check(created)

        self.assertEqual((checked["status"], checked["lastError"]), ("OK", ""))
        self.assertEqual((self.server.requests, self.server.dialed), ([], []))
