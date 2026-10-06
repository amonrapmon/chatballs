"""Основа тестов инструментов агента: MCP-сервер, HTTP-запрос и агент."""

from __future__ import annotations

from chatballs.integrations.external_server_testing import URL, order_status
from chatballs.integrations.test_external_tools import McpToolsTestCase

AGENTS_URL = "/api/v1/agents/"


class AgentToolsTestCase(McpToolsTestCase):
    """У сервера «Магазин» два инструмента: get_order_status сервер отметил
    «только чтение», cancel_order — нет."""

    def setUp(self) -> None:
        super().setUp()
        self.mcp = self._refresh(self._server())
        self.http = self._http()
        self.agent = self._agent("Приёмная")

    def _http(self, name: str = "Статус заказа", **settings: object) -> dict:
        response = self._create("HTTP", order_status(**settings), name=name)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["integration"]

    def _agent(self, name: str) -> dict:
        response = self.client.post(AGENTS_URL, {"name": name}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["agent"]

    def _servers(self, agent: dict | None = None) -> dict[int, dict]:
        """Блок «Инструменты» карточки: сервер по идентификатору."""
        response = self.client.get(f"{AGENTS_URL}{(agent or self.agent)['id']}/")
        self.assertEqual(response.status_code, 200, response.content)
        return {server["integrationId"]: server for server in response.json()["agent"]["tools"]}

    def _enabled(self, agent: dict | None = None) -> set[tuple[int, str]]:
        return {
            (server_id, tool["name"])
            for server_id, server in self._servers(agent).items()
            for tool in server["tools"]
            if tool["enabled"]
        }

    def _set_tools(self, *tools: tuple[dict, str], agent: dict | None = None):
        body = {"tools": [{"integrationId": server["id"], "name": name} for server, name in tools]}
        return self.client.patch(f"{AGENTS_URL}{(agent or self.agent)['id']}/", body, format="json")

    def _enable(self, *tools: tuple[dict, str], agent: dict | None = None) -> None:
        response = self._set_tools(*tools, agent=agent)
        self.assertEqual(response.status_code, 200, response.content)

    def _confirm(self, name: str = "cancel_order", confirmed: object = True):
        return self.client.post(
            f"{URL}{self.mcp['id']}/tools/read-only/confirm/",
            {"name": name, "confirmed": confirmed},
            format="json",
        )

    def _revoke(self, name: str = "cancel_order"):
        return self.client.post(
            f"{URL}{self.mcp['id']}/tools/read-only/revoke/", {"name": name}, format="json"
        )

    def _patch_server(self, server: dict, **body: object) -> dict:
        response = self.client.patch(f"{URL}{server['id']}/", body, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["integration"]
