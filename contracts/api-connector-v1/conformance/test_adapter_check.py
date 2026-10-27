"""Independent tests: no Django settings, database, provider or network required.

The existing stdlib FakeAdapter is loaded as a file (not as a Chatballs
package). All HTTP requests are to a local server and synthetic recipients.
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import adapter_check
from fixtures import command_text


def load_reference_adapter():
    path = (
        Path(__file__).resolve().parents[3]
        / "apps/backend/chatballs/api_connector/testing_fake_adapter.py"
    )
    spec = importlib.util.spec_from_file_location("isolated_fake_adapter", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("standalone reference adapter not found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FakeAdapter


class ContractFixtureTests(unittest.TestCase):
    def test_offline_v1_shapes_without_backend(self):
        results = adapter_check.fixture_checks()
        self.assertGreaterEqual(len(results), 10)
        self.assertEqual([r.name for r in results if not r.passed], [])

    def test_refuses_remote_or_redirecting_adapter_destinations(self):
        for url in (
            "https://example.com/v1/commands",
            "http://192.168.1.20:9081/v1/commands",
            "http://127.0.0.1:9081/elsewhere",
            "http://127.0.0.1:9081/v1/commands?token=secret",
            "http://user:pass@127.0.0.1:9081/v1/commands",
            "file:///tmp/v1/commands",
            "http://127.0.0.1/v1/commands",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                adapter_check.loopback_url(url)

    def test_command_fixture_has_no_credentials_or_provider_ids(self):
        doc = command_text()
        encoded = json.dumps(doc)
        self.assertIn("conformance-NO-REAL-SEND", encoded)
        self.assertNotIn("Bearer", encoded)
        self.assertNotIn("apiKey", encoded)


class ReferenceAdapterProtocolTests(unittest.TestCase):
    def test_loopback_http_protocol_command_replay_auth_and_conflict(self):
        FakeAdapter = load_reference_adapter()
        with FakeAdapter(source_id="connection-2") as adapter:
            results = adapter_check.protocol_checks(
                adapter.url, token=adapter.token, source_id="connection-2",
            )
            self.assertEqual(
                [r.name for r in results if not r.passed], [],
                msg=str(results),
            )
            self.assertEqual(len(adapter.commands), 1)
            journal = adapter.journal.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(journal), 1)
            self.assertNotIn(adapter.token, journal[0])
            self.assertEqual(adapter.commands[0]["recipient"]["external_chat_id"], "conformance-NO-REAL-SEND")

    def test_cli_json_output_with_local_sandbox_is_machine_readable(self):
        FakeAdapter = load_reference_adapter()
        with FakeAdapter(source_id="connection-2") as adapter:
            stream = io.StringIO()
            with (
                patch.dict(os.environ, {"ADAPTER_CONFORMANCE_TOKEN": adapter.token}),
                redirect_stdout(stream),
            ):
                result = adapter_check.main(
                    ["--adapter-url", adapter.url, "--source-id", "connection-2", "--json"]
                )
            self.assertEqual(result, 0)
            report = json.loads(stream.getvalue())
            self.assertEqual(report["passed"], report["total"])
            self.assertGreaterEqual(report["total"], 17)
            self.assertNotIn(adapter.token, stream.getvalue())
            self.assertEqual(len(adapter.commands), 1)


if __name__ == "__main__":
    unittest.main()
