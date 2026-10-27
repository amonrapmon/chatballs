"""Deterministic, provider-free wire fixtures for independent API Connector v1 adapters.

No Django, database, Chatballs settings or remote networking dependencies.
Synthetic route identifiers are intentionally NOT real messenger identities.
"""
from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

SOURCE_ID = "connection-2"
COMMAND_UUID = "66778171-9aa2-58e9-b2c4-9fc96c1bed4d"
UTC_TIME = "2026-10-27T12:00:00Z"
SYNTHETIC_CHAT = "conformance-NO-REAL-SEND"
SYNTHETIC_USER = "conformance-NO-REAL-SEND"


def created_text(*, source_id=SOURCE_ID, event_id="fixture-inbound-1"):
    return {
        "schema": "chatballs.api-connector.event.v1",
        "source_id": source_id,
        "event": {"id": event_id, "type": "message.created", "occurred_at": UTC_TIME},
        "conversation": {"external_chat_id": SYNTHETIC_CHAT},
        "sender": {"external_user_id": SYNTHETIC_USER, "display_name": "Synthetic Guest"},
        "message": {
            "external_message_id": "provider-synthetic-in-1",
            "direction": "inbound", "origin": "external_observed",
            "actor": "contact", "kind": "text",
            "text": "Synthetic incoming message", "attachments": [],
        },
    }


def observed_outgoing(*, source_id=SOURCE_ID, event_id="fixture-observed-1"):
    item = created_text(source_id=source_id, event_id=event_id)
    item["event"]["type"] = "message.observed_outgoing"
    item["sender"]["external_user_id"] = "remote-synthetic-operator"
    item["message"].update({
        "external_message_id": "provider-synthetic-out-1",
        "direction": "outbound", "actor": "unknown",
        "text": "Synthetic external reply",
    })
    return item


def echo(*, source_id=SOURCE_ID, event_id="fixture-echo-1", command_id=COMMAND_UUID):
    return {
        "schema": "chatballs.api-connector.event.v1",
        "source_id": source_id,
        "event": {"id": event_id, "type": "message.echo", "occurred_at": UTC_TIME},
        "conversation": {"external_chat_id": SYNTHETIC_CHAT},
        "echo": {
            "origin": "command_echo", "command_id": command_id,
            "external_message_id": "provider-synthetic-sent-1",
        },
    }


def receipt(
    *, source_id=SOURCE_ID, event_id="fixture-receipt-1",
    command_id=COMMAND_UUID, status="PROVIDER_SENT",
):
    item = {
        "schema": "chatballs.api-connector.receipt.v1",
        "source_id": source_id,
        "event": {"id": event_id, "occurred_at": UTC_TIME},
        "command_id": command_id, "status": status,
    }
    if status == "FAILED":
        item["failure_code"] = "synthetic_failure"
    else:
        item["provider_message_id"] = "provider-synthetic-sent-1"
    return item


def inbound_media(*, source_id=SOURCE_ID):
    blob = b"%PDF-1.4\n1 0 obj\nendobj\n%%EOF\n"
    item = created_text(source_id=source_id, event_id="fixture-media-1")
    item["message"].update({
        "kind": "file", "text": "",
        "attachments": [{
            "filename": "synthetic.pdf", "content_type": "application/pdf",
            "size_bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest(),
        }],
    })
    return item, blob


def command_text(*, source_id=SOURCE_ID, command_id=None):
    return {
        "schema": "chatballs.api-connector.command.v1",
        "source_id": source_id,
        "command_id": command_id or str(uuid4()),
        "recipient": {
            "external_chat_id": SYNTHETIC_CHAT,
            "external_user_id": SYNTHETIC_USER,
        },
        "route_version": "source-scoped-route-v1",
        "created_at": datetime.now(UTC).isoformat(),
        "message": {"kind": "text", "text": "Synthetic outbound, NEVER deliver", "media": []},
    }


def command_file(*, source_id=SOURCE_ID, command_id=None):
    item = command_text(source_id=source_id, command_id=command_id)
    item["message"] = {
        "kind": "file", "text": "Synthetic attachment",
        "media": [{
            "ref": "command", "filename": "synthetic.pdf",
            "content_type": "application/pdf", "size_bytes": 8,
            "sha256": hashlib.sha256(b"fake-pdf").hexdigest(),
        }],
    }
    return item


def changed_command(original):
    item = deepcopy(original)
    item["message"]["text"] = "Conflicting command, same UUID"
    return item
