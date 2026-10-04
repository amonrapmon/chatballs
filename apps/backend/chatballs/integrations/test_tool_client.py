"""Клиент инструментов: соединение с проверенным IP, перенаправления, ответ.

Сервер теста слушает loopback, куда клиент не ходит никогда, поэтому подменены
два места: DNS (имена разрешаются в «публичные» адреса) и открытие сокета —
оно ведёт на сервер теста и запоминает, какой адрес клиент просил.
"""

from __future__ import annotations

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from django.test import SimpleTestCase, override_settings

from chatballs.identity import instance_settings
from chatballs.integrations import tool_client
from chatballs.integrations.tool_client import MAX_RESPONSE_BYTES, ToolResponseRejected, fetch
from chatballs.integrations.tool_network import ToolAddressRejected
from chatballs.integrations.tool_testing import PUBLIC_IP, fake_dns

OTHER_IP = "93.184.216.35"
DNS = {
    "shop.example.test": [PUBLIC_IP],
    "cdn.example.test": [OTHER_IP],
    "intranet.example.test": ["192.168.1.20"],
    "postgres": ["172.20.0.5"],
}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    # путь → (статус, заголовки, тело)
    routes: dict[str, tuple[int, dict[str, str], bytes]] = {}
    seen: list[dict[str, str]] = []

    def _serve(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        received = self.rfile.read(length) if length else b""
        type(self).seen.append(
            {"method": self.command, "path": self.path, "body": received.decode(), **dict(self.headers.items())}
        )
        if self.path == "/slow":
            time.sleep(1.5)
        status, headers, body = type(self).routes[self.path]
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        if "Content-Length" not in headers:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:  # клиент отказался от ответа и закрыл соединение
            self.close_connection = True

    do_GET = do_POST = _serve  # noqa: N815

    def log_message(self, *args):  # тишина в выводе тестов
        return


def _json(body: bytes = b'{"status":"shipped"}', status: int = 200) -> tuple[int, dict[str, str], bytes]:
    return status, {"Content-Type": "application/json", "Content-Length": str(len(body))}, body


def _redirect(location: str, status: int = 302) -> tuple[int, dict[str, str], bytes]:
    return status, {"Location": location, "Content-Length": "0"}, b""


@override_settings(CHATBALLS_INSTANCE_SERVICE_HOSTS=["postgres"])
class ToolClientTests(SimpleTestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        _Handler.routes = {}
        _Handler.seen = []
        fake_dns(self, DNS)
        self.dialed: list[str] = []
        self._patch(tool_client, "_open_socket", self._dial)
        self.allow_private(False)
        self.base = f"http://shop.example.test:{self.port}"

    def _patch(self, target, name: str, value) -> None:
        patcher = mock.patch.object(target, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _dial(self, address: str, port: int, timeout: float) -> socket.socket:
        self.dialed.append(address)
        return socket.create_connection(("127.0.0.1", self.port), timeout)

    def allow_private(self, value: bool) -> None:
        self._patch(instance_settings, "tools_private_network_allowed", lambda: value)

    def test_connection_goes_to_the_checked_address_with_the_host_name(self) -> None:
        _Handler.routes["/orders/7"] = _json()

        response = fetch(f"{self.base}/orders/7", timeout=5, headers={"Authorization": "Bearer k"})

        self.assertEqual((response.status, response.content_type), (200, "application/json"))
        self.assertEqual(response.body, b'{"status":"shipped"}')
        self.assertEqual(self.dialed, [PUBLIC_IP])
        self.assertEqual(_Handler.seen[0]["Host"], f"shop.example.test:{self.port}")
        self.assertEqual(_Handler.seen[0]["Authorization"], "Bearer k")

    def test_post_sends_the_body(self) -> None:
        _Handler.routes["/mcp"] = _json(b"{}")

        fetch(f"{self.base}/mcp", timeout=5, method="POST", body=b'{"a":1}', headers={"Content-Type": "application/json"})

        self.assertEqual((_Handler.seen[0]["method"], _Handler.seen[0]["body"]), ("POST", '{"a":1}'))

    def test_internal_address_is_refused_without_a_connection(self) -> None:
        for url in (
            f"http://127.0.0.1:{self.port}/orders/7",
            "http://192.168.1.20/",
            "http://intranet.example.test/",
            "http://postgres:5432/",
            "http://169.254.169.254/latest/meta-data/",
        ):
            with self.subTest(url=url), self.assertRaises(ToolAddressRejected):
                fetch(url, timeout=5)
        self.assertEqual(self.dialed, [])
        self.assertEqual(_Handler.seen, [])

    def test_redirect_to_an_internal_address_is_refused(self) -> None:
        for location in (
            "http://169.254.169.254/latest/meta-data/",
            f"http://127.0.0.1:{self.port}/secret",
            "http://intranet.example.test/secret",
            "http://postgres:5432/",
            "file:///run/chatballs/secrets/secret_key",
        ):
            _Handler.routes["/start"] = _redirect(location)
            _Handler.routes["/secret"] = _json()
            self.dialed.clear()
            with self.subTest(location=location), self.assertRaises(ToolAddressRejected):
                fetch(f"{self.base}/start", timeout=5)
            # Соединение было одно — с исходным адресом.
            self.assertEqual(self.dialed, [PUBLIC_IP])

    def test_three_redirects_are_followed_and_the_fourth_is_not(self) -> None:
        _Handler.routes.update(
            {"/r1": _redirect("/r2"), "/r2": _redirect("/r3"), "/r3": _redirect("/done"), "/done": _json()}
        )

        self.assertEqual(fetch(f"{self.base}/r1", timeout=5).url, f"{self.base}/done")

        _Handler.routes["/r0"] = _redirect("/r1")
        with self.assertRaises(ToolResponseRejected) as raised:
            fetch(f"{self.base}/r0", timeout=5)
        self.assertEqual(raised.exception.code, "too_many_redirects")

    def test_redirect_to_another_host_is_checked_and_loses_secret_headers(self) -> None:
        _Handler.routes["/start"] = _redirect(f"http://cdn.example.test:{self.port}/file")
        _Handler.routes["/file"] = _json()

        fetch(f"{self.base}/start", timeout=5, headers={"Authorization": "Bearer k", "Accept": "application/json"})

        self.assertEqual(self.dialed, [PUBLIC_IP, OTHER_IP])
        self.assertNotIn("Authorization", _Handler.seen[1])
        self.assertEqual(_Handler.seen[1]["Accept"], "application/json")

    def test_oversized_response_is_refused(self) -> None:
        big = b"x" * (MAX_RESPONSE_BYTES + 1)
        _Handler.routes["/declared"] = (200, {"Content-Type": "text/plain", "Content-Length": str(len(big))}, big)
        # Без Content-Length размер выясняется только чтением.
        _Handler.routes["/stream"] = (200, {"Content-Type": "text/plain"}, big)
        _Handler.routes["/limit"] = (200, {"Content-Type": "text/plain"}, big[:-1])

        for path in ("/declared", "/stream"):
            with self.subTest(path=path), self.assertRaises(ToolResponseRejected) as raised:
                fetch(f"{self.base}{path}", timeout=5)
            self.assertEqual(raised.exception.code, "too_large")
        self.assertEqual(len(fetch(f"{self.base}/limit", timeout=5).body), MAX_RESPONSE_BYTES)

    def test_only_json_and_text_are_accepted(self) -> None:
        for content_type in ("application/json; charset=utf-8", "text/plain", "text/event-stream", "text/html"):
            _Handler.routes["/x"] = (200, {"Content-Type": content_type, "Content-Length": "2"}, b"{}")
            with self.subTest(content_type=content_type):
                self.assertEqual(fetch(f"{self.base}/x", timeout=5).body, b"{}")
        for content_type in ("application/pdf", "image/png", "application/octet-stream", "application/xml", ""):
            headers = {"Content-Length": "2"} | ({"Content-Type": content_type} if content_type else {})
            _Handler.routes["/x"] = (200, headers, b"{}")
            with self.subTest(content_type=content_type), self.assertRaises(ToolResponseRejected) as raised:
                fetch(f"{self.base}/x", timeout=5)
            self.assertEqual(raised.exception.code, "content_type")

    def test_empty_answer_without_a_type_is_accepted(self) -> None:
        _Handler.routes["/notify"] = (202, {"Content-Length": "0"}, b"")

        self.assertEqual(fetch(f"{self.base}/notify", timeout=5, method="POST", body=b"{}").status, 202)

    def test_timeout_is_set_by_the_caller(self) -> None:
        _Handler.routes["/slow"] = _json()

        started = time.monotonic()
        with self.assertRaises(OSError):
            fetch(f"{self.base}/slow", timeout=0.3)
        self.assertLess(time.monotonic() - started, 1.2)

    def test_setting_opens_private_ranges_but_not_loopback_or_services(self) -> None:
        self.allow_private(True)
        _Handler.routes["/orders/7"] = _json()

        fetch(f"http://intranet.example.test:{self.port}/orders/7", timeout=5)
        fetch(f"http://192.168.1.20:{self.port}/orders/7", timeout=5)

        self.assertEqual(self.dialed, ["192.168.1.20", "192.168.1.20"])
        for url in (f"http://127.0.0.1:{self.port}/orders/7", "http://postgres:5432/", "http://172.20.0.5/"):
            with self.subTest(url=url), self.assertRaises(ToolAddressRejected):
                fetch(url, timeout=5)
        self.assertEqual(len(self.dialed), 2)
