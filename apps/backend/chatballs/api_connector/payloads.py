"""Provider-neutral connector v1 text-event validation.

Other event/media kinds are intentionally rejected until their complete
durable handling exists. Untrusted payloads never define tenant/Integration.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json

from chatballs.conversations.transports.base import InboundMessage


class ConnectorPayloadError(ValueError):
    def __init__(self, code: str, status: int = 422):
        self.code = code
        self.status = status
        super().__init__(code)


@dataclass(frozen=True)
class ParsedTextEvent:
    source_id: str
    event_id: str
    external_message_id: str
    inbound: InboundMessage
    fingerprint: str


def _object(value: object, allowed: set[str], required: set[str]) -> dict:
    if not isinstance(value, dict) or not required.issubset(value) or set(value) - allowed:
        raise ConnectorPayloadError("invalid_payload", 400)
    return value


def _identifier(value: object, limit: int) -> str:
    if not isinstance(value, str) or not 0 < len(value) <= limit or value != value.strip():
        raise ConnectorPayloadError("invalid_payload", 400)
    return value


def _optional(value: object, limit: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str) or len(value) > limit:
        raise ConnectorPayloadError("invalid_payload", 400)
    return value


def _utc_timestamp(value: object) -> None:
    if not isinstance(value, str) or len(value) > 40 or not value.endswith("Z"):
        raise ConnectorPayloadError("invalid_payload", 400)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ConnectorPayloadError("invalid_payload", 400) from error
    if parsed.utcoffset() != timedelta(0):
        raise ConnectorPayloadError("invalid_payload", 400)


def parse_text_event(payload: object) -> ParsedTextEvent:
    body = _object(
        payload,
        {"schema", "source_id", "event", "conversation", "sender", "message"},
        {"schema", "source_id", "event", "conversation", "sender", "message"},
    )
    if body["schema"] != "chatballs.api-connector.event.v1":
        raise ConnectorPayloadError("unsupported_schema", 422)
    source_id = _identifier(body["source_id"], 128)
    event = _object(body["event"], {"id", "type", "occurred_at"}, {"id", "type", "occurred_at"})
    event_id = _identifier(event["id"], 256)
    _utc_timestamp(event["occurred_at"])
    if event["type"] != "message.created":
        raise ConnectorPayloadError("unsupported_event_type", 422)

    conversation = _object(body["conversation"], {"external_chat_id", "thread"}, {"external_chat_id"})
    chat_id = _identifier(conversation["external_chat_id"], 128)
    if conversation.get("thread") is not None:
        raise ConnectorPayloadError("unsupported_capability", 422)

    sender = _object(
        body["sender"],
        {"external_user_id", "display_name", "username", "avatar_ref", "phone"},
        {"external_user_id"},
    )
    user_id = _identifier(sender["external_user_id"], 128)
    display_name = _optional(sender.get("display_name"), 255) or "Guest"
    username = _optional(sender.get("username"), 128)
    if sender.get("avatar_ref") is not None or sender.get("phone") is not None:
        raise ConnectorPayloadError("unsupported_capability", 422)

    message = _object(
        body["message"],
        {
            "external_message_id", "direction", "origin", "actor", "kind",
            "text", "html", "attachments", "reply_to_external_message_id", "contact_share",
        },
        {"external_message_id", "direction", "origin", "actor", "kind", "text", "attachments"},
    )
    external_message_id = _identifier(message["external_message_id"], 128)
    if (
        message["direction"] != "inbound" or message["origin"] != "external_observed"
        or message["actor"] != "contact"
    ):
        raise ConnectorPayloadError("unsupported_capability", 422)
    if message["kind"] != "text":
        raise ConnectorPayloadError("unsupported_capability", 422)
    text = message["text"]
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise ConnectorPayloadError("invalid_payload", 400)
    if not isinstance(message["attachments"], list):
        raise ConnectorPayloadError("invalid_payload", 400)
    if (
        message["attachments"]
        or message.get("html") is not None
        or message.get("contact_share") is not None
        or message.get("reply_to_external_message_id") is not None
    ):
        raise ConnectorPayloadError("unsupported_capability", 422)

    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    return ParsedTextEvent(
        source_id=source_id,
        event_id=event_id,
        external_message_id=external_message_id,
        inbound=InboundMessage(
            external_id=external_message_id, user_id=user_id, chat_id=chat_id,
            text=text, display_name=display_name, username=username,
        ),
        fingerprint=digest,
    )
