"""Observed external outgoing text through an authenticated API Connector.

These are provider-observed messages, not Chatballs commands. They are stored
in the native Conversation/Message history without inventing an employee,
reusing the Contact inbound handler, or sending anything to the provider.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from django.db import transaction

from chatballs.api_connector.delivery_correlation import lock_current_connector
from chatballs.api_connector.payloads import (
    ConnectorPayloadError,
    _identifier,
    _object,
    _optional,
    _utc_timestamp,
)
from chatballs.conversations.external_outgoing import (
    ExternalOutgoingConflict,
    record_external_outgoing,
)
from chatballs.i18n import t
from chatballs.integrations.connector_settings import mirror_is_current
from chatballs.integrations.models import Integration
from chatballs.notifications.models import NotificationAudience, NotificationType
from chatballs.notifications.services import notify
from chatballs.tenancy.context import TenantContext


@dataclass(frozen=True)
class ObservedOutgoing:
    source_id: str
    event_id: str
    chat_id: str
    external_message_id: str
    text: str
    occurred_at: datetime
    observed_at: datetime | None
    reply_to_message_id: str
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
        body["event"], {"id", "type", "occurred_at", "observed_at"}, {"id", "type", "occurred_at"},
    )
    if event["type"] != "message.observed_outgoing":
        raise ConnectorPayloadError("unsupported_event_type", 422)
    event_id = _identifier(event["id"], 256)
    occurred_at = _utc_timestamp(event["occurred_at"])
    observed_at = _utc_timestamp(event["observed_at"]) if "observed_at" in event else None

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
    if message["attachments"] or message.get("html") is not None or message.get("contact_share") is not None:
        raise ConnectorPayloadError("unsupported_capability", 422)
    reply_to = message.get("reply_to_external_message_id")
    reply_to_message_id = _identifier(reply_to, 128) if reply_to is not None else ""
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return ObservedOutgoing(
        source_id=source_id, event_id=event_id, chat_id=chat_id,
        external_message_id=external_message_id, text=value,
        occurred_at=occurred_at, observed_at=observed_at, reply_to_message_id=reply_to_message_id,
        fingerprint=hashlib.sha256(encoded).hexdigest(),
    )


@transaction.atomic
def ingest_observed_outgoing(integration: Integration, event: ObservedOutgoing) -> None:
    """Serialize the current setting with edits before applying any effects."""
    if event.source_id != f"connection-{integration.pk}":
        raise ConnectorPayloadError("source_mismatch", 409)
    # Keep Connector lock ordering (Integration -> Conversation).
    # Inbound takes the same Integration lock after its organization lock,
    # so neither path can race contact/route creation. Never take the
    # organization lock here: AI publication owns it before Integration.
    current = lock_current_connector(integration)
    if not mirror_is_current(current.config, occurred_at=event.occurred_at, observed_at=event.observed_at):
        return
    try:
        created = record_external_outgoing(
            connection=current, source=f"api_connector:{current.pk}",
            event_id=event.event_id, fingerprint=event.fingerprint,
            external_chat_id=event.chat_id,
            external_message_id=event.external_message_id, text=event.text,
            occurred_at=event.occurred_at, reply_to_message_id=event.reply_to_message_id,
        )
    except ExternalOutgoingConflict as error:
        raise ConnectorPayloadError(error.code, 409) from error
    if created is not None:
        # An operator-initiated first contact is an inbox conversation, not
        # an incoming guest message: don't queue an AI turn or invent an
        # assigned employee. Notify staff only once for the newly created route.
        notify(
            context=TenantContext.for_resource(current.organization),
            type=NotificationType.NEW_DIALOG,
            audience=NotificationAudience.OPERATORS,
            audience_group=created.group,
            title=f"Новый диалог · {current.channel.name}",
            body=f"{created.contact.name or 'Гость'} · {current.provider}: {event.text[:80]}",
            title_key="notifications.new_dialog",
            body_key="notifications.new_dialog_body",
            text_params={
                "channel": current.channel.name,
                "contact": created.contact.name or t("conversations.guest"),
                "provider": current.provider,
                "preview": event.text[:80],
            },
            target_id=created.pk,
            source_type="Conversation", source_id=created.pk,
            dedup_key=f"dialog:{created.pk}",
        )
