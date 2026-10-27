"""Correlate a provider's own-send echo with a native Connector command.

An echo observes an already-created message. It must NEVER create a Message,
enqueue an Outbox command, manufacture an operator identity, or advance the
provider delivery state. Delivery evidence is handled by receipt.v1 only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from chatballs.api_connector.payloads import (
    ConnectorPayloadError,
    _identifier,
    _object,
    _utc_timestamp,
)
from chatballs.conversations.inbound_dedup import _already_processed
from chatballs.conversations.models import Message, MessageAuthor
from chatballs.integrations.models import Integration
from chatballs.tenancy.context import TenantContext


@dataclass(frozen=True)
class ConnectorEcho:
    source_id: str
    event_id: str
    external_chat_id: str
    command_id: str
    external_message_id: str
    fingerprint: str


def _optional_identifier(value: object, limit: int) -> str:
    if value is None:
        return ""
    return _identifier(value, limit)


def parse_connector_echo(payload: object) -> ConnectorEcho:
    body = _object(
        payload, {"schema", "source_id", "event", "conversation", "echo"},
        {"schema", "source_id", "event", "conversation", "echo"},
    )
    if body["schema"] != "chatballs.api-connector.event.v1":
        raise ConnectorPayloadError("unsupported_schema", 422)

    source_id = _identifier(body["source_id"], 128)
    event = _object(
        body["event"], {"id", "type", "occurred_at"}, {"id", "type", "occurred_at"},
    )
    event_id = _identifier(event["id"], 256)
    _utc_timestamp(event["occurred_at"])
    if event["type"] != "message.echo":
        raise ConnectorPayloadError("unsupported_event_type", 422)

    conversation = _object(
        body["conversation"], {"external_chat_id", "thread"}, {"external_chat_id"},
    )
    chat_id = _identifier(conversation["external_chat_id"], 128)
    if conversation.get("thread") is not None:
        raise ConnectorPayloadError("unsupported_capability", 422)

    echo = _object(
        body["echo"], {"origin", "command_id", "external_message_id"}, {"origin"},
    )
    if echo["origin"] != "command_echo":
        raise ConnectorPayloadError("unsupported_capability", 422)
    command_id = _optional_identifier(echo.get("command_id"), 36)
    external_message_id = _optional_identifier(echo.get("external_message_id"), 128)
    if not command_id and not external_message_id:
        raise ConnectorPayloadError("invalid_payload", 400)
    if command_id:
        try:
            if str(UUID(command_id)) != command_id:
                raise ValueError("noncanonical")
        except (ValueError, AttributeError) as error:
            raise ConnectorPayloadError("invalid_payload", 400) from error

    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return ConnectorEcho(
        source_id=source_id, event_id=event_id, external_chat_id=chat_id,
        command_id=command_id, external_message_id=external_message_id,
        fingerprint=hashlib.sha256(encoded).hexdigest(),
    )


@transaction.atomic
def correlate_connector_echo(connection: Integration, echo: ConnectorEcho) -> None:
    """Record the correlation in the existing operator Message, never send.

    An unknown command/provider ID is retryable (409): do not consume the
    event ID until an existing message has been found. The enclosing tenant
    transaction makes InboxEvent dedup and message changes atomic.
    """
    if echo.source_id != f"connection-{connection.pk}":
        raise ConnectorPayloadError("source_mismatch", 409)

    messages = Message.objects.select_for_update().filter(
        organization_id=connection.organization_id,
        conversation__connection_id=connection.pk,
        conversation__external_chat_id=echo.external_chat_id,
        author_type=MessageAuthor.OPERATOR,
    )
    if echo.command_id:
        messages = messages.filter(connector_delivery__commandId=echo.command_id)
    else:
        # Provider-ID-only echoes are meaningful only after a receipt or
        # command-correlated echo persisted that identity. Never guess by text.
        messages = messages.filter(
            connector_delivery__providerMessageId=echo.external_message_id,
        )
    message = messages.first()
    if message is None:
        raise ConnectorPayloadError("unknown_command", 409)

    delivery = message.connector_delivery or {}
    previous_provider_id = delivery.get("providerMessageId", "")
    if (echo.external_message_id and previous_provider_id
            and echo.external_message_id != previous_provider_id):
        raise ConnectorPayloadError("echo_conflict", 409)

    if echo.external_message_id and Message.objects.filter(
        organization_id=connection.organization_id,
        conversation__connection_id=connection.pk,
        connector_delivery__providerMessageId=echo.external_message_id,
    ).exclude(pk=message.pk).exists():
        raise ConnectorPayloadError("echo_conflict", 409)

    try:
        duplicate = _already_processed(
            TenantContext.for_resource(connection.organization),
            f"api_connector_echo:{connection.pk}", echo.event_id, "",
            payload_hash=echo.fingerprint,
        )
    except ValueError as error:
        if str(error) == "connector_event_id_conflict":
            raise ConnectorPayloadError("id_conflict", 409) from error
        raise
    if duplicate:
        return

    new_delivery = {**delivery, "echoObservedAt": timezone.now().isoformat()}
    if echo.external_message_id and not previous_provider_id:
        new_delivery["providerMessageId"] = echo.external_message_id
    # A provider echo is not proof of provider send, delivery, or read.
    # Preserve even the QUEUED state unchanged; receipt.v1 owns transitions.
    message.connector_delivery = new_delivery
    message.save(update_fields=["connector_delivery"])
