"""Поддельный MCP-сервер для тестов: Streamable HTTP на loopback.

Клиент инструментов на loopback не ходит, поэтому открытие сокета подменено:
соединение с «публичным» адресом из подменённого DNS ведёт на этот сервер.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from chatballs.integrations import tool_client

# Текст, которого не должно быть ни в ошибках, ни в ответах API.
UPSTREAM_SECRET = "upstream-internal-detail"

ORDER_STATUS = {
    "name": "get_order_status",
    "title": "Статус заказа",
    "description": "Возвращает статус и время доставки заказа по номеру",
    "inputSchema": {
        "type": "object",
        "properties": {"order_number": {"type": "string"}},
        "required": ["order_number"],
    },
    "annotations": {"readOnlyHint": True},
}
CANCEL_ORDER = {
    "name": "cancel_order",
    "description": "Отменяет заказ, если кухня ещё не начала готовить",
    "inputSchema": {"type": "object", "properties": {"order_number": {"type": "string"}}},
}


class FakeMcpServer:
    """Настройки и журнал сервера; меняются прямо в тесте."""

    def __init__(self) -> None:
        self.tools: list[dict] = [ORDER_STATUS, CANCEL_ORDER]
        # Если задан — сервер требует такой заголовок Authorization.
        self.token = ""
        self.delay = 0.0
        self.sse = False
        self.page_size = 0
        self.session_id = "session-1"
        self.call_result: dict = {"content": [{"type": "text", "text": "Заказ в пути"}]}
        # Не MCP: любой запрос получает страницу сайта.
        self.html = False
        self.requests: list[dict] = []
        self.dialed: list[str] = []
        self.port = 0

    @property
    def methods(self) -> list[str]:
        return [request["rpc"] for request in self.requests]

    def start(self, test_case) -> str:
        """Запустить сервер и вернуть его адрес для настроек интеграции."""
        handler = type("Handler", (_Handler,), {"fake": self})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()
        test_case.addCleanup(server.server_close)
        test_case.addCleanup(server.shutdown)
        patcher = mock.patch.object(tool_client, "_open_socket", self._dial)
        patcher.start()
        test_case.addCleanup(patcher.stop)
        return self.url()

    def url(self, host: str = "mcp.example.test") -> str:
        return f"http://{host}:{self.port}/mcp"

    def _dial(self, address: str, port: int, timeout: float) -> socket.socket:
        self.dialed.append(address)
        return socket.create_connection(("127.0.0.1", self.port), timeout)

    def answer(self, method: str, params: dict) -> dict:
        """Тело ответа JSON-RPC без ``id``: ``result`` или ``error``."""
        if method == "initialize":
            return {
                "result": {
                    "protocolVersion": params.get("protocolVersion"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake", "version": "1"},
                }
            }
        if method == "tools/list":
            start = int(params.get("cursor") or 0)
            size = self.page_size or len(self.tools) or 1
            result: dict = {"tools": self.tools[start : start + size]}
            if start + size < len(self.tools):
                result["nextCursor"] = str(start + size)
            return {"result": result}
        if method == "tools/call" and any(tool["name"] == params.get("name") for tool in self.tools):
            return {"result": self.call_result}
        return {"error": {"code": -32602, "message": f"Unknown: {UPSTREAM_SECRET}"}}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    fake: FakeMcpServer

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        message = json.loads(self.rfile.read(length) or b"{}")
        self._record(message.get("method", ""), message.get("params") or {})
        if self.fake.delay:
            time.sleep(self.fake.delay)
        if self.fake.token and self.headers.get("Authorization") != self.fake.token:
            return self._reply(401, "application/json", json.dumps({"error": UPSTREAM_SECRET}))
        if self.fake.html:
            return self._reply(200, "text/html", f"<html>{UPSTREAM_SECRET}</html>")
        if "id" not in message:
            return self._reply(202)
        answer = {"jsonrpc": "2.0", "id": message["id"], **self.fake.answer(message["method"], message.get("params") or {})}
        extra = {"Mcp-Session-Id": self.fake.session_id} if message["method"] == "initialize" else {}
        if self.fake.sse:
            body = f"event: message\ndata: {json.dumps(answer)}\n\n"
            return self._reply(200, "text/event-stream", body, extra)
        self._reply(200, "application/json", json.dumps(answer), extra)

    def do_DELETE(self) -> None:  # noqa: N802
        self._record("DELETE", {})
        self._reply(200)

    def _record(self, rpc: str, params: dict) -> None:
        headers = {name.lower(): value for name, value in self.headers.items()}
        self.fake.requests.append({"rpc": rpc, "params": params, "headers": headers})

    def _reply(self, status: int, content_type: str = "", body: str = "", extra: dict | None = None) -> None:
        payload = body.encode()
        self.send_response(status)
        if content_type:
            self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(payload)
        except OSError:  # клиент не дождался ответа и закрыл соединение
            self.close_connection = True

    def log_message(self, *args):  # тишина в выводе тестов
        return
