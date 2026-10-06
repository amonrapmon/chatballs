"""MCP-клиент против поддельного сервера: сеанс, список, вызов, ошибки."""

from __future__ import annotations

import time
from unittest import mock

from django.test import SimpleTestCase, override_settings

from chatballs.identity import instance_settings
from chatballs.integrations import mcp_client
from chatballs.integrations.mcp_client import McpError, call_tool, list_tools, ping
from chatballs.integrations.mcp_testing import (
    CANCEL_ORDER,
    ORDER_STATUS,
    UPSTREAM_SECRET,
    FakeMcpServer,
)
from chatballs.integrations.tool_testing import PUBLIC_IP, fake_dns

DNS = {"mcp.example.test": [PUBLIC_IP], "intranet.example.test": ["192.168.1.20"]}
HEADERS = {"Authorization": "Bearer shop-secret-token"}


@override_settings(CHATBALLS_INSTANCE_SERVICE_HOSTS=["postgres"])
class McpClientTests(SimpleTestCase):
    def setUp(self) -> None:
        fake_dns(self, DNS)
        patcher = mock.patch.object(instance_settings, "tools_private_network_allowed", lambda: False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.server = FakeMcpServer()
        self.url = self.server.start(self)

    def _code(self, action) -> str:
        with self.assertRaises(McpError) as raised:
            action()
        self.assertNotIn(UPSTREAM_SECRET, str(raised.exception))
        return raised.exception.code

    def test_session_initializes_lists_tools_and_closes(self) -> None:
        tools = list_tools(self.url, headers=HEADERS, timeout=5)

        self.assertEqual(tools, [ORDER_STATUS, CANCEL_ORDER])
        self.assertEqual(
            self.server.methods, ["initialize", "notifications/initialized", "tools/list", "DELETE"]
        )
        self.assertEqual(self.server.dialed[0], PUBLIC_IP)
        initialize, *later = self.server.requests
        self.assertEqual(initialize["params"]["protocolVersion"], mcp_client.PROTOCOL_VERSION)
        self.assertIn("text/event-stream", initialize["headers"]["accept"])
        self.assertNotIn("mcp-session-id", initialize["headers"])
        for request in later:
            self.assertEqual(request["headers"]["authorization"], HEADERS["Authorization"])
            self.assertEqual(request["headers"]["mcp-session-id"], "session-1")
            self.assertEqual(request["headers"]["mcp-protocol-version"], mcp_client.PROTOCOL_VERSION)

    def test_ping_only_initializes(self) -> None:
        ping(self.url, headers=HEADERS, timeout=5)

        self.assertEqual(self.server.methods, ["initialize", "notifications/initialized", "DELETE"])

    def test_tool_list_follows_pages(self) -> None:
        self.server.page_size = 1

        tools = list_tools(self.url, headers={}, timeout=5)

        self.assertEqual([tool["name"] for tool in tools], ["get_order_status", "cancel_order"])
        self.assertEqual(self.server.methods.count("tools/list"), 2)

    def test_answer_in_an_event_stream_is_read(self) -> None:
        self.server.sse = True

        self.assertEqual(len(list_tools(self.url, headers={}, timeout=5)), 2)

    def test_call_sends_arguments_and_returns_text(self) -> None:
        result = call_tool(
            self.url, "get_order_status", {"order_number": "10482"}, headers=HEADERS, timeout=5
        )

        self.assertEqual((result.text, result.is_error), ("Заказ в пути", False))
        call = next(request for request in self.server.requests if request["rpc"] == "tools/call")
        self.assertEqual(
            call["params"], {"name": "get_order_status", "arguments": {"order_number": "10482"}}
        )

    def test_call_result_shapes(self) -> None:
        self.server.call_result = {"content": [], "structuredContent": {"status": "в пути"}}
        structured = call_tool(self.url, "get_order_status", {}, headers={}, timeout=5)
        self.assertEqual(structured.text, '{"status":"в пути"}')

        self.server.call_result = {
            "content": [{"type": "text", "text": "Заказ не найден"}, {"type": "image", "data": "AAAA"}],
            "isError": True,
        }
        failed = call_tool(self.url, "get_order_status", {}, headers={}, timeout=5)
        self.assertEqual((failed.text, failed.is_error), ("Заказ не найден", True))

    def test_wrong_authorization(self) -> None:
        self.server.token = "Bearer other"

        self.assertEqual(self._code(lambda: ping(self.url, headers=HEADERS, timeout=5)), "unauthorized")

    def test_timeout(self) -> None:
        self.server.delay = 1.5

        started = time.monotonic()
        code = self._code(
            lambda: call_tool(self.url, "get_order_status", {}, headers={}, timeout=0.3)
        )

        self.assertEqual(code, "timeout")
        self.assertLess(time.monotonic() - started, 1.2)

    def test_server_refusal_carries_no_foreign_text(self) -> None:
        code = self._code(lambda: call_tool(self.url, "unknown_tool", {}, headers={}, timeout=5))

        self.assertEqual(code, "rejected")

    def test_answer_that_is_not_mcp(self) -> None:
        self.server.html = True

        self.assertEqual(self._code(lambda: ping(self.url, headers={}, timeout=5)), "bad_response")

    def test_forbidden_and_unknown_addresses_are_not_dialed(self) -> None:
        cases = (
            (self.server.url("intranet.example.test"), "address_forbidden"),
            (f"http://127.0.0.1:{self.server.port}/mcp", "address_forbidden"),
            ("http://postgres:5432/mcp", "address_forbidden"),
            (self.server.url("missing.example.test"), "unreachable"),
        )
        for url, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(self._code(lambda url=url: ping(url, headers={}, timeout=5)), expected)
        self.assertEqual(self.server.dialed, [])

    def test_closed_port_is_unreachable(self) -> None:
        with mock.patch.object(mcp_client, "fetch", side_effect=ConnectionRefusedError()):
            self.assertEqual(self._code(lambda: ping(self.url, headers={}, timeout=5)), "unreachable")
