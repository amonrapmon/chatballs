"""Standalone v1 contract verifier for a provider-disconnected loopback adapter.

Usage:
  python contracts/api-connector-v1/conformance/adapter_check.py
  ADAPTER_CONFORMANCE_TOKEN=... python contracts/api-connector-v1/conformance/adapter_check.py \
      --adapter-url http://127.0.0.1:9081/v1/commands --source-id connection-2

No Django, Chatballs runtime, n8n, provider credentials or network needed for
fixture validation. LIVE mode makes HTTP requests ONLY to loopback and MUST be
run on a sandbox adapter disconnected from real messengers.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from jsonschema import Draft202012Validator, FormatChecker

from fixtures import (
    changed_command,
    command_file,
    command_text,
    created_text,
    echo,
    inbound_media,
    observed_outgoing,
    receipt,
)

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema.json"
MAX_REPLY_BYTES = 4096


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str = ""


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def contract_validator(definition: str, schema: dict):
    return Draft202012Validator(
        {
            "$schema": schema["$schema"],
            "$defs": schema["$defs"],
            "$ref": f"#/$defs/{definition}",
        },
        format_checker=FormatChecker(),
    )


def fixture_checks() -> list[Check]:
    """Check wire fixtures even if an adapter has not been built yet."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    file_event, file_bytes = inbound_media()
    examples = [
        ("inbound_text", "MessageCreatedTextEvent", created_text()),
        ("observed_outgoing", "ObservedOutgoingEvent", observed_outgoing()),
        ("own_send_echo", "EchoEvent", echo()),
        ("inbound_file_manifest", "MessageCreatedMediaEvent", file_event),
        ("provider_sent_receipt", "DeliveryReceipt", receipt()),
        ("delivered_receipt", "DeliveryReceipt", receipt(status="DELIVERED")),
        ("failed_receipt", "DeliveryReceipt", receipt(status="FAILED")),
        ("outbound_text_command", "AdapterCommand", command_text()),
        ("outbound_file_command", "AdapterCommand", command_file()),
        ("accepted_command_ack", "CommandAck", {"accepted": True, "id": command_text()["command_id"]}),
    ]
    checks = []
    for name, definition, value in examples:
        errors = list(contract_validator(definition, schema).iter_errors(value))
        checks.append(Check(name, not errors, "schema mismatch" if errors else ""))
    checks.append(Check("inbound_file_manifest_sha256", file_event["message"]["attachments"][0]["sha256"] == __import__("hashlib").sha256(file_bytes).hexdigest()))
    return checks


def loopback_url(value: str) -> str:
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("invalid loopback adapter port") from error
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
        or port is None
        or parsed.path != "/v1/commands"
        or parsed.query or parsed.fragment
        or parsed.username or parsed.password
    ):
        raise ValueError("only exact loopback http(s)://host:port/v1/commands is permitted")
    return value


def post_command(url: str, token: str, data: dict) -> tuple[int, dict | None, str]:
    """Return status, small JSON body, and response Content-Type.

    Never follow redirects, proxy loopback traffic or print credentials/bodies.
    """
    request = Request(
        url,
        data=json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    opener = build_opener(ProxyHandler({}), NoRedirects())
    try:
        with opener.open(request, timeout=5) as result:
            status = result.status
            media_type = result.headers.get("Content-Type", "")
            raw = result.read(MAX_REPLY_BYTES + 1)
    except HTTPError as error:
        status = error.code
        media_type = error.headers.get("Content-Type", "")
        raw = error.read(MAX_REPLY_BYTES + 1)
    if len(raw) > MAX_REPLY_BYTES:
        return status, None, media_type
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        parsed = None
    return status, parsed, media_type


def protocol_checks(url: str, *, token: str, source_id: str) -> list[Check]:
    """Exercise command receiver baseline. Sender MUST be provider-disconnected."""
    if not token or len(token) < 16:
        raise ValueError("set a >=16-character synthetic Bearer in ADAPTER_CONFORMANCE_TOKEN")
    if not source_id.startswith("connection-") or not source_id[11:].isdigit():
        raise ValueError("source_id must be connection-{numeric integration id}")
    url = loopback_url(url)
    command = command_text(source_id=source_id)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    contract_validator("AdapterCommand", schema).validate(command)

    results = []

    def check_status(name: str, payload: dict, secret: str, expected_status: int, *, expect_ack=False):
        try:
            status, body, content_type = post_command(url, secret, payload)
        except (OSError, URLError, TimeoutError):
            results.append(Check(name, False, "adapter unavailable"))
            return False
        valid = status == expected_status
        if expect_ack:
            ack = contract_validator("CommandAck", schema)
            valid = (
                valid
                and content_type.lower().split(";", 1)[0].strip() == "application/json"
                and isinstance(body, dict)
                and ack.is_valid(body)
                and body.get("id") == command["command_id"]
            )
        results.append(Check(name, bool(valid), "" if valid else f"unexpected HTTP status/ack (status={status})"))
        return bool(valid)

    check_status("unauthorized_bearer", command, token + "-WRONG", 401)
    created = check_status("first_command_persisted", command, token, 202, expect_ack=True)
    if created:
        check_status("identical_retry_idempotent", command, token, 200, expect_ack=True)
        check_status("changed_same_command_uuid_conflicts", changed_command(command), token, 409)
    else:
        results.append(Check("identical_retry_idempotent", False, "not run: original command rejected"))
        results.append(Check("changed_same_command_uuid_conflicts", False, "not run: original command rejected"))

    invalid = command_text(source_id=source_id)
    invalid.pop("command_id")
    check_status("missing_command_id_rejected", invalid, token, 400)
    wrong_source = command_text(source_id="connection-999999999")
    check_status("wrong_connection_source_rejected", wrong_source, token, 422)
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Provider-free API Connector v1 conformance")
    parser.add_argument("--adapter-url", help="Explicit opt-in: local sandbox /v1/commands HTTP endpoint")
    parser.add_argument("--source-id", default="connection-2", help="Expected source ID in the sandbox")
    parser.add_argument("--token-env", default="ADAPTER_CONFORMANCE_TOKEN", help="Name of env var holding sandbox Bearer. The value is never printed.")
    parser.add_argument("--json", action="store_true", help="Machine-readable check results")
    args = parser.parse_args(argv)
    try:
        results = fixture_checks()
        if args.adapter_url:
            results.extend(protocol_checks(
                args.adapter_url,
                token=os.environ.get(args.token_env, ""),
                source_id=args.source_id,
            ))
    except (ValueError, OSError) as error:
        # Errors here contain no remote payload or credential.
        parser.error(str(error))
    passed = sum(item.passed for item in results)
    if args.json:
        print(json.dumps({"passed": passed, "total": len(results), "checks": [asdict(x) for x in results]}, ensure_ascii=False))
    else:
        for result in results:
            print(f'{"PASS" if result.passed else "FAIL"} {result.name}' + (f": {result.detail}" if result.detail else ""))
        print(f"{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
