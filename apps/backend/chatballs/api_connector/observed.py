"""Observed external outgoing text through an authenticated API Connector.

These are provider-observed messages, not Chatballs commands. They are stored
in the native Conversation/Message history without inventing an employee,
reusing the Contact inbound handler, or sending anything to the provider.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from chatballs.api_connector.payloads import (
    ConnectorPayloadError,
    _identifier,
    _object,
    _optional,
    _utc_timestamp,
)
from chatballs.conversations.inbound_dedup import _already_processed
from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    ExpectedResponder,
    LifecycleState,
    Message,
    MessageAuthor,
)
from chatballs.conversations.queue import QUEUE_FIELDS, enter_queue
from chatballs.conversations.domain_events import operation_key, record_queue_entry
from chatballs.conversations.rules import reply_reminder
from chatballs.integrations.models import Integration
from chatballs.tenancy.context import TenantContext


@dataclass(frozen=True)
class ObservedOutgoing:
    source_id: str
    event_id: str
    chat_id: str
    external_message_id: str
    text: str
    fingerprint: str


def parse_observed_outgoing(payload: object) -> ObservedOutgoing:
    body = _object(
        payload,
        {"schema", "source_id", "event", "conversation", "sender", "message"},
        {"schema", "source_id", "event", "conversation", "sender", "message"},
    )
    if body["schema"] != "chatballs.api-connector.event.v1":
        raise ConnectorPayloadError("unsupported_schema", 422)
    source_id = _identifier(body["source_id"], 128)
    event = _object(
        body["event"], {"id", "type", "occurred_at"}, {"id", "type", "occurred_at"},
    )
    if event["type"] != "message.observed_outgoing":
        raise ConnectorPayloadError("unsupported_event_type", 422)
    event_id = _identifier(event["id"], 256)
    _utc_timestamp(event["occurred_at"])

    conversation = _object(
        body["conversation"], {"external_chat_id", "thread"}, {"external_chat_id"},
    )
    chat_id = _identifier(conversation["external_chat_id"], 128)
    if conversation.get("thread") is not None:
        raise ConnectorPayloadError("unsupported_capability", 422)

    # The sender describes a remote actor. It is NEVER a Chatballs staff ID.
    sender = _object(
        body["sender"],
        {"external_user_id", "display_name", "username", "avatar_ref", "phone"},
        {"external_user_id"},
    )
    _identifier(sender["external_user_id"], 128)
    _optional(sender.get("display_name"), 255)
    _optional(sender.get("username"), 128)
    if sender.get("avatar_ref") is not None or sender.get("phone") is not None:
        raise ConnectorPayloadError("unsupported_capability", 422)

    message = _object(
        body["message"],
        {
            "external_message_id", "direction", "origin", "actor", "kind",
            "text", "html", "attachments", "reply_to_external_message_id",
            "contact_share",
        },
        {"external_message_id", "direction", "origin", "actor", "kind", "text", "attachments"},
    )
    external_message_id = _identifier(message["external_message_id"], 128)
    if (message["direction"], message["origin"], message["actor"]) != (
        "outbound", "external_observed", "unknown",
    ):
        raise ConnectorPayloadError("unsupported_capability", 422)
    if message["kind"] != "text":
        raise ConnectorPayloadError("unsupported_capability", 422)
    value = message["text"]
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise ConnectorPayloadError("invalid_payload", 400)
    if not isinstance(message["attachments"], list):
        raise ConnectorPayloadError("invalid_payload", 400)
    if (message["attachments"] or message.get("html") is not None
            or message.get("contact_share") is not None
            or message.get("reply_to_external_message_id") is not None):
        raise ConnectorPayloadError("unsupported_capability", 422)
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return ObservedOutgoing(
        source_id=source_id, event_id=event_id, chat_id=chat_id,
        external_message_id=external_message_id, text=value,
        fingerprint=hashlib.sha256(encoded).hexdigest(),
    )


@transaction.atomic
def ingest_observed_outgoing(integration: Integration, event: ObservedOutgoing) -> None:
    if event.source_id != f"connection-{integration.pk}":
        raise ConnectorPayloadError("source_mismatch", 409)

    # Unknown conversations must be retried after real inbound, not created
    # from a forged/unsolicited provider operator event.
    conversation = (
        Conversation.objects.select_for_update()
        .filter(
            organization_id=integration.organization_id,
            connection=integration,
            external_chat_id=event.chat_id,
            lifecycle=LifecycleState.OPEN,
        ).order_by("-last_activity_at", "-pk").first()
    )
    if conversation is None:
        raise ConnectorPayloadError("unknown_conversation", 409)

    existing = (
        Message.objects.filter(
            conversation=conversation, external_id=event.external_message_id,
        ).first()
    )
    if existing and (
        existing.connector_origin != "EXTERNAL_OBSERVED"
        or existing.author_type != MessageAuthor.OPERATOR
        or existing.text != event.text
    ):
        raise ConnectorPayloadError("external_message_id_conflict", 409)

    # If the observed event is actually an echo of our own command, the
    # adapter must send message.echo instead, not duplicate our original.
    if Message.objects.filter(
        conversation=conversation,
        connector_delivery__providerMessageId=event.external_message_id,
    ).exists():
        raise ConnectorPayloadError("echo_expected", 409)

    try:
        duplicate = _already_processed(
            TenantContext.for_resource(integration.organization),
            f"api_connector_observed:{integration.pk}", event.event_id, "",
            payload_hash=event.fingerprint,
        )
    except ValueError as error:
        if str(error) == "connector_event_id_conflict":
            raise ConnectorPayloadError("id_conflict", 409) from error
        raise
    if duplicate or existing:
        return

    Message.objects.create(
        conversation=conversation,
        author_type=MessageAuthor.OPERATOR,
        author_user=None,
        kind="",
        text=event.text,
        external_id=event.external_message_id,
        connector_origin="EXTERNAL_OBSERVED",
    )
    conversation.last_activity_at = timezone.now()
    fields = ["last_activity_at"]
    if conversation.control_mode == ControlMode.AI:
        # Pause automatic answers without claiming any internal employee.
        entered = enter_queue(conversation)
        fields.extend(QUEUE_FIELDS)
    else:
        entered = False
        if conversation.control_mode == ControlMode.HUMAN:
            # An external reply did reach the guest; local assignment remains
            # unchanged and no fake public-reply statistic is recorded.
            conversation.expected_responder = ExpectedResponder.CUSTOMER
            fields.append("expected_responder")
    conversation.save(update_fields=fields)
    record_queue_entry(
        conversation, entered=entered,
        operation_id=operation_key(
            f"api_connector_observed:{integration.pk}", event.event_id,
        ),
        actor_kind="SYSTEM", connection=integration,
    )
    if conversation.control_mode == ControlMode.HUMAN:
        reply_reminder.reconcile(conversation)
