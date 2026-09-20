from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from chatballs.conversations.transports.base import InboundMessage


class GatewayPayloadError(ValueError):
    """The request body is not a valid v1 gateway inbound payload."""


class UnsupportedGatewayChatError(GatewayPayloadError):
    """The payload is valid but its chat type is outside Phase 2."""


class UnsupportedGatewayDeliveryStatusError(GatewayPayloadError):
    """The payload status is outside the delivery-status contract."""


@dataclass(frozen=True, slots=True)
class GatewayInboundPayload:
    source_id: str
    inbound: InboundMessage


@dataclass(frozen=True, slots=True)
class GatewayDeliveryStatusPayload:
    source_id: str
    command_id: UUID
    external_chat_id: str
    external_message_id: str | None
    status: str
    occurred_at: datetime | None
    failure_kind: str | None


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


def parse_delivery_status_payload(payload: object) -> GatewayDeliveryStatusPayload:
    body = _object(payload, "payload")
    schema = _required_string(body.get("schema"), "schema")
    if schema != "intercom-gw.chatballs.delivery-status.v1":
        raise GatewayPayloadError("unsupported schema")

    source_id = _required_string(body.get("source_id"), "source_id")
    command_text = _required_string(body.get("command_id"), "command_id", max_length=64)
    try:
        command_id = UUID(command_text)
    except ValueError as error:
        raise GatewayPayloadError("command_id must be a UUID") from error

    external_chat_id = _required_string(
        body.get("external_chat_id"), "external_chat_id", max_length=128
    )
    status = body.get("status")
    if not isinstance(status, str) or not status.strip():
        raise GatewayPayloadError("status is required")
    status = status.strip()
    supported_statuses = {"provider_accepted", "delivered", "read", "failed", "no_account"}
    if status not in supported_statuses:
        raise UnsupportedGatewayDeliveryStatusError("unsupported delivery status")

    external_message_id = body.get("external_message_id")
    if external_message_id is not None:
        if not isinstance(external_message_id, str) or not external_message_id.strip():
            raise GatewayPayloadError("external_message_id must be a non-empty string or null")
        external_message_id = external_message_id.strip()
        if len(external_message_id) > 128:
            raise GatewayPayloadError("external_message_id is too long")
    if status in {"provider_accepted", "delivered", "read"} and not external_message_id:
        raise GatewayPayloadError("external_message_id is required for this status")

    failure_kind = body.get("failure_kind")
    if failure_kind is not None and failure_kind not in {"provider_failed", "no_account"}:
        raise GatewayPayloadError("unsupported failure_kind")

    return GatewayDeliveryStatusPayload(
        source_id=source_id,
        command_id=command_id,
        external_chat_id=external_chat_id,
        external_message_id=external_message_id,
        status=status,
        occurred_at=_optional_timestamp(body.get("occurred_at")),
        failure_kind=failure_kind,
    )
