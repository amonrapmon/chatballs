from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from chatballs.conversations.transports.base import InboundMessage


class GatewayPayloadError(ValueError):
    """The request body is not a valid v1 gateway inbound payload."""


class UnsupportedGatewayChatError(GatewayPayloadError):
    """The payload is valid but its chat type is outside Phase 2."""


@dataclass(frozen=True, slots=True)
class GatewayInboundPayload:
    source_id: str
    inbound: InboundMessage


def _object(value: object, field: str) -> dict:
    if not isinstance(value, dict):
        raise GatewayPayloadError(f"{field} must be an object")
    return value


def _required_string(value: object, field: str, *, max_length: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GatewayPayloadError(f"{field} is required")
    result = value.strip()
    if max_length is not None and len(result) > max_length:
        raise GatewayPayloadError(f"{field} is too long")
    return result


def _optional_string(value: object, field: str, *, max_length: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise GatewayPayloadError(f"{field} must be a string or null")
    result = value.strip()
    if len(result) > max_length:
        raise GatewayPayloadError(f"{field} is too long")
    return result


def _optional_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise GatewayPayloadError("occurred_at must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise GatewayPayloadError("occurred_at must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise GatewayPayloadError("occurred_at must be a UTC timestamp")
    return parsed


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GatewayPayloadError(f"{field} is required")
    return value


def parse_inbound_payload(payload: object) -> GatewayInboundPayload:
    body = _object(payload, "payload")
    schema = _required_string(body.get("schema"), "schema")
    if schema != "intercom-gw.chatballs.inbound.v1":
        raise GatewayPayloadError("unsupported schema")

    source_id = _required_string(body.get("source_id"), "source_id")
    event_id = _required_string(body.get("event_id"), "event_id", max_length=256)
    occurred_at = _optional_timestamp(body.get("occurred_at"))

    chat = _object(body.get("chat"), "chat")
    chat_id = _required_string(chat.get("external_chat_id"), "chat.external_chat_id", max_length=128)
    chat_type = _required_string(chat.get("type"), "chat.type")
    if chat_type != "personal":
        raise UnsupportedGatewayChatError("unsupported chat type")

    sender = _object(body.get("sender"), "sender")
    user_id = _required_string(sender.get("external_user_id"), "sender.external_user_id", max_length=128)
    display_name = _optional_string(sender.get("display_name"), "sender.display_name", max_length=255) or "Guest"
    username = _optional_string(sender.get("username"), "sender.username", max_length=128)
    phone = _optional_string(sender.get("phone"), "sender.phone", max_length=32)
    avatar_url = _optional_string(sender.get("avatar_url"), "sender.avatar_url", max_length=512)

    message = _object(body.get("message"), "message")
    message_id = _required_string(
        message.get("external_message_id"),
        "message.external_message_id",
        max_length=128,
    )
    reply_to_id = _optional_string(
        message.get("reply_to_message_id"),
        "message.reply_to_message_id",
        max_length=128,
    )
    text = _required_text(message.get("text"), "message.text")

    return GatewayInboundPayload(
        source_id=source_id,
        inbound=InboundMessage(
            external_id=message_id,
            external_event_id=event_id,
            external_occurred_at=occurred_at,
            external_reply_to_id=reply_to_id,
            user_id=user_id,
            chat_id=chat_id,
            text=text,
            display_name=display_name,
            username=username,
            phone=phone,
            avatar_url=avatar_url,
        ),
    )
