"""MCP-клиент по Streamable HTTP: ``initialize``, ``tools/list``, ``tools/call``.

Каждое обращение — короткий сеанс: ``initialize``, уведомление
``notifications/initialized``, сам запрос и завершение сеанса. В сеть клиент
ходит только через ``tool_client.fetch`` — с проверкой адреса, перенаправлений
и ответа (SPEC-0023 R-2, R-16, R-18). Срок задаёт вызывающий, и он один на
весь сеанс.

Любая неудача — ``McpError`` с кодом. Текста чужого сервера в ошибке нет:
ни тела ответа, ни сообщения JSON-RPC (R-5, R-13).
"""

from __future__ import annotations

import http.client
import json
import time
from dataclasses import dataclass

from chatballs.integrations.tool_client import ToolResponse, ToolResponseRejected, fetch
from chatballs.integrations.tool_network import ToolAddressRejected

PROTOCOL_VERSION = "2025-06-18"
# Streamable HTTP появился в 2025-03-26; более старый сервер нам не подходит.
SUPPORTED_VERSIONS = frozenset({"2025-03-26", PROTOCOL_VERSION})
# Сервер, который вечно отдаёт nextCursor, не должен занять весь срок.
MAX_TOOL_PAGES = 20
_CLOSE_TIMEOUT_SECONDS = 3.0

UNREACHABLE = "unreachable"
TIMEOUT = "timeout"
UNAUTHORIZED = "unauthorized"
ADDRESS_FORBIDDEN = "address_forbidden"
BAD_RESPONSE = "bad_response"
REJECTED = "rejected"


class McpError(Exception):
    """Обращение к MCP-серверу не удалось; ``code`` — причина без чужого текста."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class McpToolResult:
    text: str
    # Инструмент отработал, но сообщил об ошибке (``isError``).
    is_error: bool


def ping(url: str, *, headers: dict[str, str], timeout: float) -> None:
    """Проверить соединение: сервер отвечает на ``initialize``."""
    with _Session(url, headers, timeout):
        pass


def list_tools(url: str, *, headers: dict[str, str], timeout: float) -> list[dict]:
    """Инструменты сервера, как их отдал ``tools/list`` (все страницы)."""
    with _Session(url, headers, timeout) as session:
        tools: list[dict] = []
        cursor = None
        for _ in range(MAX_TOOL_PAGES):
            result = session.request("tools/list", {"cursor": cursor} if cursor else {})
            page = result.get("tools")
            if not isinstance(page, list):
                raise McpError(BAD_RESPONSE)
            tools.extend(tool for tool in page if isinstance(tool, dict))
            cursor = result.get("nextCursor")
            if not cursor:
                return tools
        raise McpError(BAD_RESPONSE)


def call_tool(
    url: str, name: str, arguments: dict, *, headers: dict[str, str], timeout: float
) -> McpToolResult:
    with _Session(url, headers, timeout) as session:
        result = session.request("tools/call", {"name": name, "arguments": arguments})
    content = result.get("content")
    texts = [
        str(item.get("text", ""))
        for item in (content if isinstance(content, list) else [])
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    text = "\n".join(part for part in texts if part)
    if not text and result.get("structuredContent") is not None:
        text = json.dumps(result["structuredContent"], ensure_ascii=False, separators=(",", ":"))
    return McpToolResult(text=text, is_error=bool(result.get("isError")))


class _Session:
    def __init__(self, url: str, headers: dict[str, str], timeout: float) -> None:
        self._url = url
        self._headers = dict(headers)
        self._deadline = time.monotonic() + timeout
        self._session_headers: dict[str, str] = {}
        self._session_id = ""
        self._last_id = 0

    def __enter__(self) -> _Session:
        result = self.request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "Chatballs", "version": "1"},
            },
        )
        version = result.get("protocolVersion")
        if version not in SUPPORTED_VERSIONS:
            raise McpError(BAD_RESPONSE)
        self._session_headers["MCP-Protocol-Version"] = version
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return self

    def __exit__(self, *exc_info: object) -> None:
        """Завершить сеанс на сервере; неудача здесь ничего не меняет."""
        if not self._session_id:
            return
        left = min(self._deadline - time.monotonic(), _CLOSE_TIMEOUT_SECONDS)
        if left <= 0:
            return
        try:
            fetch(self._url, timeout=left, method="DELETE", headers=self._request_headers())
        except (
            ToolAddressRejected,
            ToolResponseRejected,
            OSError,
            http.client.HTTPException,
            ValueError,
        ):
            pass

    def request(self, method: str, params: dict) -> dict:
        self._last_id += 1
        request_id = self._last_id
        response = self._send(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        if method == "initialize":
            self._session_id = response.headers.get("mcp-session-id", "")
        message = _answer(response, request_id)
        if "error" in message:
            raise McpError(REJECTED)
        result = message.get("result")
        if not isinstance(result, dict):
            raise McpError(BAD_RESPONSE)
        return result

    def _request_headers(self) -> dict[str, str]:
        headers = {**self._headers, **self._session_headers}
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return headers

    def _send(self, payload: dict) -> ToolResponse:
        left = self._deadline - time.monotonic()
        if left <= 0:
            raise McpError(TIMEOUT)
        headers = {
            **self._request_headers(),
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        try:
            response = fetch(
                self._url,
                timeout=left,
                method="POST",
                headers=headers,
                body=json.dumps(payload).encode(),
            )
        except ToolAddressRejected as error:
            code = UNREACHABLE if error.code == "unresolved" else ADDRESS_FORBIDDEN
            raise McpError(code) from error
        except ToolResponseRejected as error:
            raise McpError(BAD_RESPONSE) from error
        except TimeoutError as error:
            raise McpError(TIMEOUT) from error
        except (OSError, http.client.HTTPException, ValueError) as error:
            raise McpError(UNREACHABLE) from error
        if response.status in (401, 403):
            raise McpError(UNAUTHORIZED)
        if response.status >= 400:
            raise McpError(BAD_RESPONSE)
        return response


def _answer(response: ToolResponse, request_id: int) -> dict:
    """Найти ответ JSON-RPC на свой запрос — в JSON или в потоке событий."""
    text = response.body.decode("utf-8", errors="replace")
    documents = _event_data(text) if response.content_type == "text/event-stream" else [text]
    for document in documents:
        try:
            parsed = json.loads(document)
        except ValueError:
            continue
        for message in parsed if isinstance(parsed, list) else [parsed]:
            if (
                isinstance(message, dict)
                and message.get("id") == request_id
                and ("result" in message or "error" in message)
            ):
                return message
    raise McpError(BAD_RESPONSE)


def _event_data(stream: str) -> list[str]:
    """Поля ``data`` событий SSE: одно событие — одно сообщение JSON-RPC."""
    events: list[str] = []
    lines: list[str] = []
    for line in [*stream.splitlines(), ""]:
        if line.startswith("data:"):
            lines.append(line[5:].removeprefix(" "))
        elif not line and lines:
            events.append("\n".join(lines))
            lines = []
    return events
