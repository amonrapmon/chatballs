"""Инструменты в карточке агента: что доступно, что включено (SPEC-0023 R-9)."""

from __future__ import annotations

from chatballs.ai.agent_tools_testing import AGENTS_URL, AgentToolsTestCase
from chatballs.ai.models import AgentTool
from chatballs.i18n import t
from chatballs.integrations.external_server_testing import URL, order_status
from chatballs.integrations.mcp_testing import ORDER_STATUS

STATUS = "get_order_status"
CANCEL = "cancel_order"


class AgentToolsCardTests(AgentToolsTestCase):
    def test_card_lists_servers_with_their_tools(self) -> None:
        servers = self._servers()
        self.assertIsNotNone(servers[self.mcp["id"]].pop("lastCheckedAt"))

        self.assertEqual(
            servers[self.mcp["id"]],
            {
                "integrationId": self.mcp["id"],
                "name": "Магазин",
                "type": "mcp",
                "isActive": True,
                "status": "OK",
                "lastError": "",
                "lastErrorCode": "",
                "tools": [
                    {
                        "name": STATUS,
                        "title": "Статус заказа",
                        "description": "Возвращает статус и время доставки заказа по номеру",
                        "readOnly": True,
                        "enabled": False,
                    },
                    {
                        "name": CANCEL,
                        "title": CANCEL,
                        "description": "Отменяет заказ, если кухня ещё не начала готовить",
                        "readOnly": False,
                        "enabled": False,
                    },
                ],
            },
        )
        self.assertEqual(
            servers[self.http["id"]]["tools"],
            [
                {
                    "name": STATUS,
                    "title": "Статус заказа",
                    "description": "Статус заказа по номеру",
                    "readOnly": True,
                    "enabled": False,
                }
            ],
        )

    def test_tools_are_served_separately_from_the_card(self) -> None:
        self._enable((self.mcp, STATUS))

        response = self.client.get(f"{AGENTS_URL}{self.agent['id']}/tools/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json()["tools"],
            self.client.get(f"{AGENTS_URL}{self.agent['id']}/").json()["agent"]["tools"],
        )
        self.assertEqual(self.client.get(f"{AGENTS_URL}0/tools/").status_code, 404)

    def test_agent_list_does_not_carry_tools(self) -> None:
        items = self.client.get(AGENTS_URL).json()["items"]

        self.assertTrue(items)
        self.assertNotIn("tools", items[0])

    def test_enabled_tools_apply_at_once_and_only_to_this_agent(self) -> None:
        other = self._agent("Продажи")

        response = self._set_tools((self.mcp, STATUS), (self.http, STATUS))

        self.assertEqual(response.status_code, 200, response.content)
        expected = {(self.mcp["id"], STATUS), (self.http["id"], STATUS)}
        saved = {
            (server["integrationId"], tool["name"])
            for server in response.json()["agent"]["tools"]
            for tool in server["tools"]
            if tool["enabled"]
        }
        self.assertEqual(saved, expected)
        self.assertEqual(self._enabled(), expected)
        self.assertEqual(self._enabled(other), set())
        row = AgentTool.objects.get(integration_id=self.mcp["id"])
        self.assertEqual(row.organization_id, self.organization.id)

    def test_the_list_replaces_the_previous_set(self) -> None:
        self._enable((self.mcp, STATUS), (self.http, STATUS))

        self._enable((self.http, STATUS))

        self.assertEqual(self._enabled(), {(self.http["id"], STATUS)})

    def test_other_card_fields_do_not_touch_tools(self) -> None:
        self._enable((self.mcp, STATUS))

        response = self.client.patch(
            f"{AGENTS_URL}{self.agent['id']}/", {"persona": "Вежливый помощник"}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._enabled(), {(self.mcp["id"], STATUS)})

    def test_renamed_http_request_stays_enabled(self) -> None:
        self._enable((self.http, STATUS))

        self._patch_server(self.http, externalServer=order_status(toolName="order_state"))

        self.assertEqual(self._enabled(), {(self.http["id"], "order_state")})


class AgentToolsReadOnlyTests(AgentToolsTestCase):
    def _rejected(self, response, key: str, **params: object) -> None:
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["detail"], t(key, **params))
        self.assertFalse(AgentTool.objects.exists())

    def test_mcp_tool_without_the_mark_and_confirmation_is_rejected(self) -> None:
        # Вместе с разрешённым: отказ не должен сохранить и его.
        response = self._set_tools((self.mcp, STATUS), (self.mcp, CANCEL))

        self._rejected(response, "ai.agent_tool_may_change_data", tool=CANCEL)

    def test_confirmed_mcp_tool_can_be_enabled(self) -> None:
        self.assertEqual(self._confirm().status_code, 200)

        self._enable((self.mcp, CANCEL))

        self.assertEqual(self._enabled(), {(self.mcp["id"], CANCEL)})
        self.assertTrue(self._servers()[self.mcp["id"]]["tools"][1]["readOnly"])

    def test_post_request_without_the_read_only_mark_is_rejected(self) -> None:
        post = self._http(name="Поиск товаров", toolName="search_products", method="POST")

        self.assertFalse(self._servers()[post["id"]]["tools"][0]["readOnly"])
        self._rejected(
            self._set_tools((post, "search_products")),
            "ai.agent_tool_post_not_read_only",
            tool="Поиск товаров",
        )

    def test_post_request_with_the_read_only_mark_can_be_enabled(self) -> None:
        post = self._http(
            name="Поиск товаров", toolName="search_products", method="POST", readOnly=True
        )

        self._enable((post, "search_products"))

        self.assertEqual(self._enabled(), {(post["id"], "search_products")})

    def test_tool_of_a_disabled_server_is_rejected(self) -> None:
        self._patch_server(self.mcp, isActive=False)

        self._rejected(
            self._set_tools((self.mcp, STATUS)), "ai.agent_tool_server_disabled", server="Магазин"
        )

    def test_unknown_tool_server_and_malformed_list_are_rejected(self) -> None:
        provider = self.client.post(
            URL, {"provider": "DEMO", "name": "Демо"}, format="json"
        ).json()["integration"]

        self._rejected(self._set_tools((self.mcp, "drop_database")), "ai.agent_tool_not_found")
        self._rejected(self._set_tools((provider, STATUS)), "ai.agent_tool_not_found")
        self._rejected(self._set_tools(({"id": 10**9}, STATUS)), "ai.agent_tool_not_found")
        for body in ({"tools": "all"}, {"tools": [STATUS]}, {"tools": [{"integrationId": "1"}]}):
            response = self.client.patch(f"{AGENTS_URL}{self.agent['id']}/", body, format="json")
            self._rejected(response, "ai.agent_tools_invalid")


class AgentToolsSwitchOffTests(AgentToolsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.other = self._agent("Продажи")
        self.assertEqual(self._confirm().status_code, 200)
        for agent in (self.agent, self.other):
            self._enable((self.mcp, STATUS), (self.mcp, CANCEL), (self.http, STATUS), agent=agent)

    def _everywhere(self) -> set[tuple[int, str]]:
        """Что включено у обоих агентов; у них должно быть одинаково."""
        enabled = self._enabled(self.agent)
        self.assertEqual(self._enabled(self.other), enabled)
        self.assertEqual(AgentTool.objects.count(), 2 * len(enabled))
        return enabled

    def test_disabling_a_server_switches_its_tools_off_for_all_agents(self) -> None:
        self._patch_server(self.mcp, isActive=False)

        self.assertEqual(self._everywhere(), {(self.http["id"], STATUS)})
        # Включение сервера обратно само инструменты не возвращает.
        self._patch_server(self.mcp, isActive=True)
        self.assertEqual(self._everywhere(), {(self.http["id"], STATUS)})

    def test_disabling_an_http_request_switches_it_off_for_all_agents(self) -> None:
        self._patch_server(self.http, isActive=False)

        self.assertEqual(self._everywhere(), {(self.mcp["id"], STATUS), (self.mcp["id"], CANCEL)})

    def test_deleting_a_server_switches_its_tools_off_for_all_agents(self) -> None:
        response = self.client.delete(f"{URL}{self.mcp['id']}/")

        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(self._everywhere(), {(self.http["id"], STATUS)})

    def test_revoking_the_confirmation_switches_the_tool_off_for_all_agents(self) -> None:
        self.assertEqual(self._revoke().status_code, 200)

        self.assertEqual(self._everywhere(), {(self.mcp["id"], STATUS), (self.http["id"], STATUS)})

    def test_post_request_that_lost_the_mark_is_switched_off(self) -> None:
        self._patch_server(self.http, externalServer=order_status(method="POST"))

        self.assertEqual(self._everywhere(), {(self.mcp["id"], STATUS), (self.mcp["id"], CANCEL)})

    def test_refresh_switches_off_tools_the_server_no_longer_marks_or_lists(self) -> None:
        self.assertEqual(self._revoke().status_code, 200)
        self.server.tools = [{**ORDER_STATUS, "annotations": {}}]

        self._refresh(self.mcp)

        self.assertEqual(self._everywhere(), {(self.http["id"], STATUS)})
