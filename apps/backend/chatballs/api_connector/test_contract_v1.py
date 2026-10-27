"""Executable v1 wire conformance: schema shapes against running DTO parsers.

Requires jsonschema in the CI contract step; not an application dependency.
The versioned contract lives in contracts/api-connector-v1, not old R&D.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from django.test import TestCase

from chatballs.api_connector.outbound import CONNECTOR_OUTBOUND_REQUESTED
from chatballs.conversations.models import Conversation
from chatballs.events.models import OutboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.testing import TenantAPIClient, system_tenant_context

from chatballs.api_connector.echo import parse_connector_echo
from chatballs.api_connector.observed import parse_observed_outgoing
from chatballs.api_connector.payloads import (
    ConnectorPayloadError,
    parse_media_event,
    parse_text_event,
)
from chatballs.api_connector.receipts import parse_delivery_receipt

CONTRACT_DIR = Path(__file__).resolve().parents[4] / "contracts" / "api-connector-v1"
SCHEMA = json.loads((CONTRACT_DIR / "schema.json").read_text(encoding="utf-8"))
OPENAPI = json.loads((CONTRACT_DIR / "openapi.json").read_text(encoding="utf-8"))
WHEN = "2026-10-27T12:00:00Z"
COMMAND_ID = "66778171-9aa2-58e9-b2c4-9fc96c1bed4d"


def validator(name):
    return Draft202012Validator(
        {"$schema": SCHEMA["$schema"], "$defs": SCHEMA["$defs"], "$ref": f"#/$defs/{name}"},
        format_checker=FormatChecker(),
    )


def envelope(event_type="message.created", *, event_id="event-1"):
    return {
        "schema": "chatballs.api-connector.event.v1",
        "source_id": "connection-2",
        "event": {"id": event_id, "type": event_type, "occurred_at": WHEN},
        "conversation": {"external_chat_id": "chat-1", "thread": None},
    }


def inbound():
    return {
        **envelope(),
        "sender": {
            "external_user_id": "guest-1", "display_name": "Guest",
            "username": None, "avatar_ref": None,
        },
        "message": {
            "external_message_id": "provider-1", "direction": "inbound",
            "origin": "external_observed", "actor": "contact",
            "kind": "text", "text": "Hello", "attachments": [],
            "reply_to_external_message_id": None, "contact_share": None, "html": None,
        },
    }


def media():
    blob = b"%PDF-1.4\n1 0 obj\nendobj\n%%EOF\n"
    event = inbound()
    event["message"]["kind"] = "file"
    event["message"]["text"] = ""
    event["message"]["attachments"] = [{
        "filename": "document.pdf", "content_type": "application/pdf",
        "size_bytes": len(blob), "sha256": hashlib.sha256(blob).hexdigest(),
    }]
    return event, blob


def observed():
    event = inbound()
    event["event"]["type"] = "message.observed_outgoing"
    event["message"]["direction"] = "outbound"
    event["message"]["actor"] = "unknown"
    return event


def echo():
    event = envelope("message.echo")
    event.pop("sender", None)
    event["echo"] = {
        "origin": "command_echo", "command_id": COMMAND_ID,
        "external_message_id": "provider-2",
    }
    return event


def receipt(status="PROVIDER_SENT"):
    data = {
        "schema": "chatballs.api-connector.receipt.v1",
        "source_id": "connection-2",
        "event": {"id": "receipt-1", "occurred_at": WHEN},
        "command_id": COMMAND_ID, "status": status,
    }
    if status == "FAILED":
        data["failure_code"] = "recipient_unavailable"
    else:
        data["provider_message_id"] = "provider-2"
    return data


def command(kind="text"):
    message = {"kind": "text", "text": "Hello guest", "media": []}
    if kind == "file":
        message = {
            "kind": "file", "text": "Your document",
            "media": [{
                "ref": "command", "filename": "document.pdf",
                "content_type": "application/pdf", "size_bytes": 12,
                "sha256": hashlib.sha256(b"%PDF-1.4\nfoo").hexdigest(),
            }],
        }
    return {
        "schema": "chatballs.api-connector.command.v1",
        "source_id": "connection-2", "command_id": COMMAND_ID,
        "recipient": {
            "external_chat_id": "chat-1", "external_user_id": "guest-1",
        },
        "route_version": "source-scoped-route-v1",
        "created_at": "2026-10-27T12:00:00+00:00", "message": message,
    }


@pytest.mark.parametrize("name,fixture", [
    ("MessageCreatedTextEvent", inbound),
    ("ObservedOutgoingEvent", observed),
    ("EchoEvent", echo),
    ("DeliveryReceipt", receipt),
    ("AdapterCommand", command),
])
def test_schema_accepts_parsed_real_wire_shapes(name, fixture):
    data = fixture()
    validator(name).validate(data)
    if name == "MessageCreatedTextEvent":
        assert parse_text_event(data).external_message_id == "provider-1"
    elif name == "ObservedOutgoingEvent":
        assert parse_observed_outgoing(data).external_message_id == "provider-1"
    elif name == "EchoEvent":
        assert parse_connector_echo(data).command_id == COMMAND_ID
    elif name == "DeliveryReceipt":
        assert parse_delivery_receipt(data).command_id == COMMAND_ID


def test_multipart_manifest_matches_real_native_parser():
    event, blob = media()
    validator("MessageCreatedMediaEvent").validate(event)
    parsed = parse_media_event(
        event, bytes_content=blob, filename="document.pdf",
        content_type="application/pdf",
    )
    assert parsed.inbound.files[0].content == blob


def test_command_file_and_adapter_ack_are_valid():
    validator("AdapterCommand").validate(command("file"))
    validator("CommandAck").validate({"accepted": True, "id": COMMAND_ID})
    validator("AcceptedEvent").validate({"accepted": True, "id": "evt-1"})
    assert not validator("CommandAck").is_valid({"accepted": False, "id": COMMAND_ID})


@pytest.mark.parametrize("case,field,value", [
    ("inbound", ("message", "actor"), "unknown"),
    ("inbound", ("message", "attachments"), [{"filename": "unsupported"}]),
    ("inbound", ("message", "text"), "   "),
    ("observed", ("message", "actor"), "operator"),
    ("observed", ("message", "kind"), "file"),
    ("echo", ("echo", "origin"), "external_observed"),
    ("echo", ("echo", "command_id"), "invalid-uuid"),
    ("receipt", ("status",), "READ"),
    ("receipt", ("failure_code",), "unsafe raw provider text"),
])
def test_invalid_envelopes_rejected_by_schema(case, field, value):
    makers = {
        "inbound": ("MessageCreatedTextEvent", inbound),
        "observed": ("ObservedOutgoingEvent", observed),
        "echo": ("EchoEvent", echo),
        "receipt": ("DeliveryReceipt", receipt),
    }
    name, maker = makers[case]
    doc = deepcopy(maker())
    item = doc
    for key in field[:-1]:
        item = item[key]
    item[field[-1]] = value
    assert not validator(name).is_valid(doc)


def test_receipt_failure_code_is_conditional_and_parser_consistent():
    good = receipt("FAILED")
    validator("DeliveryReceipt").validate(good)
    assert parse_delivery_receipt(good).status == "FAILED"
    for patch in ({"failure_code": None}, {"failure_code": "raw sensitive error message"}, {}):
        bad = deepcopy(good)
        if patch:
            bad.update(patch)
        else:
            bad.pop("failure_code")
        assert not validator("DeliveryReceipt").is_valid(bad)
        with pytest.raises(ConnectorPayloadError):
            parse_delivery_receipt(bad)


def test_echo_needs_a_correlatable_identity():
    event = echo()
    event["echo"] = {"origin": "command_echo"}
    assert not validator("EchoEvent").is_valid(event)
    with pytest.raises(ConnectorPayloadError):
        parse_connector_echo(event)


def test_wire_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(SCHEMA)
    for definition in SCHEMA["$defs"].values():
        Draft202012Validator.check_schema(definition)


def test_openapi_31_references_only_implemented_schemas_and_endpoints():
    assert OPENAPI["openapi"] == "3.1.0"
    assert OPENAPI["jsonSchemaDialect"] == SCHEMA["$schema"]
    assert OPENAPI["info"]["version"].endswith("-draft")
    paths = OPENAPI["paths"]
    assert set(paths) == {
        "/api/v1/api-connector/organizations/{connector_organization_public_id}/integrations/{integration_id}/events/",
        "/api/v1/api-connector/organizations/{connector_organization_public_id}/integrations/{integration_id}/commands/{command_id}/attachment/",
        "/api/v1/organizations/{organization_public_id}/integrations/{integration_id}/connector-credential/",
        "/api/v1/organizations/{organization_public_id}/integrations/{integration_id}/connector-transport/",
        "/v1/commands",
    }
    assert "AdapterBearer" in paths["/v1/commands"]["post"]["security"][0]
    def walk_refs(node):
        if isinstance(node, dict):
            if "$ref" in node:
                yield node["$ref"]
            for value in node.values():
                yield from walk_refs(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk_refs(value)

    refs = list(walk_refs(OPENAPI))
    assert refs, "OpenAPI must expose the canonical JSON Schema components"
    for ref in refs:
        assert ref.startswith("./schema.json#/$defs/"), ref
        assert ref.split("/")[-1] in SCHEMA["$defs"]


def test_no_unimplemented_features_are_advertised():
    routes = " ".join(OPENAPI["paths"])
    for disallowed in ("/receipts/", "/media/uploads", "/capabilities/", "/v1/events"):
        assert disallowed not in routes
    spec = OPENAPI["paths"][
        "/api/v1/api-connector/organizations/{connector_organization_public_id}/integrations/{integration_id}/events/"
    ]["post"]
    assert set(spec["requestBody"]["content"]) == {"application/json", "multipart/form-data"}
    assert "ConnectorBearer" in spec["security"][0]
    assert "202" in spec["responses"]


class LiveOutboxContractTests(TestCase):
    """Validate the actual immutable operator command emitted by native Chatballs."""

    def setUp(self):
        result = bootstrap_owner(
            email="connector-wire-contract@example.com",
            password="Temporary-Test-Password!",
        )
        self.organization, self.owner = result.organization, result.owner
        self.client = TenantAPIClient()
        self.client.force_login(self.owner)
        self.connection = create_integration(
            context=system_tenant_context(self.organization),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR,
                name="Wire contract adapter",
                config={"connectorService": "custom_adapter"},
            ),
        )
        credentials = self.client.post(
            f"/api/v1/integrations/{self.connection.pk}/connector-credential/",
            data={}, format="json",
        )
        self.assertEqual(credentials.status_code, 201)
        self.token = credentials.data["token"]
        self.webhook = credentials.data["webhookPath"]

    def test_native_outbox_command_conforms_to_v1_schema(self):
        configured = self.client.post(
            f"/api/v1/integrations/{self.connection.pk}/connector-transport/",
            data={"url": "http://127.0.0.1:9081/v1/commands",
                  "token": "contract-adapter-command-token-123456"},
            format="json",
        )
        self.assertEqual(configured.status_code, 200)
        event = inbound()
        event["source_id"] = f"connection-{self.connection.pk}"
        created = self.client.post(
            self.webhook, event, format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(created.status_code, 202, created.data)
        conversation = Conversation.objects.get()
        response = self.client.post(
            f"/api/v1/conversations/{conversation.pk}/messages/",
            data={"text": "Live Outbox reply"}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        outbox = OutboxEvent.objects.get(event_type=CONNECTOR_OUTBOUND_REQUESTED)
        command_payload = outbox.payload["command"]
        validator("AdapterCommand").validate(command_payload)
        self.assertEqual(
            command_payload["command_id"],
            response.data["message"]["connectorDelivery"]["commandId"],
        )
        self.assertEqual(command_payload["message"]["kind"], "text")
        self.assertEqual(command_payload["source_id"], f"connection-{self.connection.pk}")
