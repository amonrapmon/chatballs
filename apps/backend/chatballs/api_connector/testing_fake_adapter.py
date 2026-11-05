"""Independent loopback test receiver for API Connector text commands.

No Chatballs modules, ORM or Green API dependencies. A 202 is emitted only
after appending and fsyncing a command fingerprint to a local journal.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class FakeAdapter:
    token = "local-fake-adapter-token-123456"

    def __init__(self, *, source_id: str):
        self.source_id = source_id
        self.commands: list[dict] = []
        self.digests: dict[str, str] = {}
        self.lock = threading.Lock()
        self.tempdir = tempfile.TemporaryDirectory()
        self.journal = Path(self.tempdir.name) / "commands.jsonl"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/v1/commands"

    def _handler(self):
        adapter = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                # Test credentials and request bodies must never reach logs.
                pass

            def respond(self, code: int, data: dict):
                encoded = json.dumps(data).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_POST(self):
                if self.path != "/v1/commands":
                    return self.respond(404, {"error": "not_found"})
                if not hmac.compare_digest(
                    self.headers.get("Authorization", ""), f"Bearer {adapter.token}",
                ):
                    return self.respond(401, {"error": "unauthorized"})
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if size < 1 or size > 16384:
                        return self.respond(413, {"error": "payload_too_large"})
                    command = json.loads(self.rfile.read(size))
                    if (
                        command.get("schema") != "chatballs.api-connector.command.v1"
                        or command.get("source_id") != adapter.source_id
                        or command.get("message", {}).get("kind") != "text"
                    ):
                        return self.respond(422, {"error": "invalid_payload"})
                    canonical = json.dumps(
                        command, sort_keys=True, ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode()
                    digest = hashlib.sha256(canonical).hexdigest()
                    key = command["command_id"]
                except (ValueError, KeyError, TypeError, AttributeError):
                    return self.respond(400, {"error": "invalid_payload"})
                with adapter.lock:
                    old = adapter.digests.get(key)
                    if old is not None:
                        return self.respond(
                            200 if old == digest else 409,
                            {"accepted": old == digest, "id": key},
                        )
                    record = json.dumps({"command_id": key, "hash": digest})
                    with adapter.journal.open("a", encoding="utf-8") as file:
                        file.write(record + "\n")
                        file.flush()
                        os.fsync(file.fileno())
                    adapter.digests[key] = digest
                    adapter.commands.append(command)
                return self.respond(202, {"accepted": True, "id": key})

        return Handler

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tempdir.cleanup()
