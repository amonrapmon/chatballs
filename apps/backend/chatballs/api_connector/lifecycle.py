"""Strict, provider-neutral, opt-in two-phase inbound media DTOs.

Metadata event creates a visible native Message before any provider download.
Ready attaches verified bytes to that SAME Message; failed exposes typed reason.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from chatballs.api_connector.payloads import (
    ConnectorPayloadError,
    _identifier,
    _object,
    _optional,
    _provider_phone,
    _utc_timestamp,
    parse_media_event,
)

SCHEMA = "chatballs.api-connector.event.v1"
LIFECYCLE_TYPES = {
    "message.media.announced",
    "message.media.ready",
    "message.media.failed",
}
MEDIA_KINDS = {"image", "document", "voice", "audio", "video", "animation"}
MAX_PARTS_PER_ROOT = 10
FAILURE_REASONS = {
    "PROVIDER_QUOTA", "PROVIDER_UNAVAILABLE", "EXPIRED",
    "UNSUPPORTED_KIND", "INVALID_MEDIA", "UNKNOWN",
}


@dataclass(frozen=True)
class LifecycleEvent:
    source_id: str
    event_id: str
    event_type: str
    chat_id: str
    external_message_id: str
    fingerprint: str
    kind: str = ""
    duration_seconds: int = 0
    part_index: int = 0
    caption: str = ""
    sender_id: str = ""
    display_name: str = ""
    username: str = ""
    provider_phone: str = ""
    reason: str = ""
    retryable: bool = False
    file_bytes: bytes = b""
    filename: str = ""
    content_type: str = ""
    sha256: str = ""


def parse_lifecycle_event(
    payload: object, *, file_bytes: bytes | None = None,
    filename: str = "", content_type: str = "",
) -> LifecycleEvent:
    if not isinstance(payload, dict):
        raise ConnectorPayloadError("invalid_payload", 400)
    event_info = payload.get("event")
    event_type = event_info.get("type") if isinstance(event_info, dict) else None
    if event_type not in LIFECYCLE_TYPES:
        raise ConnectorPayloadError("unsupported_event_type", 422)
    is_announce = event_type == "message.media.announced"
    is_ready = event_type == "message.media.ready"
    body = _object(
        payload,
        {"schema", "source_id", "event", "conversation", "media", "sender"}
        if is_announce else {"schema", "source_id", "event", "conversation", "media"},
        {"schema", "source_id", "event", "conversation", "media", "sender"}
        if is_announce else {"schema", "source_id", "event", "conversation", "media"},
    )
    if body["schema"] != SCHEMA:
        raise ConnectorPayloadError("unsupported_schema", 422)
    source_id = _identifier(body["source_id"], 128)
    event = _object(
        body["event"], {"id", "type", "occurred_at"}, {"id", "type", "occurred_at"},
    )
    event_id = _identifier(event["id"], 256)
    _utc_timestamp(event["occurred_at"])
    conversation = _object(
        body["conversation"], {"external_chat_id", "thread"}, {"external_chat_id"},
    )
    chat_id = _identifier(conversation["external_chat_id"], 128)
    if conversation.get("thread") is not None:
        raise ConnectorPayloadError("unsupported_capability", 422)

    common = {"external_message_id", "part_index"}
    media_allowed = (
        common | {"kind", "caption", "duration_seconds"} if is_announce
        else common | {"manifest"} if is_ready
        else common | {"reason", "retryable"}
    )
    media = _object(body["media"], media_allowed, media_allowed)
    external_message_id = _identifier(media["external_message_id"], 128)
    part_index = media["part_index"]
    if type(part_index) is not int or not 0 <= part_index < MAX_PARTS_PER_ROOT:
        raise ConnectorPayloadError("unsupported_capability", 422)

    kind = caption = sender_id = display_name = username = provider_phone = ""
    duration_seconds = 0
    reason = digest = ""
    retryable = False
    if is_announce:
        kind = media["kind"]
        caption = media["caption"]
        if not isinstance(kind, str) or kind not in MEDIA_KINDS or not isinstance(caption, str) or len(caption) > 4000:
            raise ConnectorPayloadError("unsupported_capability", 422)
        if kind == "voice" and caption:
            raise ConnectorPayloadError("unsupported_capability", 422)
        duration_seconds = media.get("duration_seconds", 0)
        if type(duration_seconds) is not int or not 0 <= duration_seconds <= 86400:
            raise ConnectorPayloadError("invalid_payload", 400)
        if kind != "voice" and duration_seconds:
            raise ConnectorPayloadError("unsupported_capability", 422)
        sender = _object(
            body["sender"],
            {"external_user_id", "display_name", "username", "avatar_ref", "phone"},
            {"external_user_id"},
        )
        sender_id = _identifier(sender["external_user_id"], 128)
        username = _optional(sender.get("username"), 128).strip()
        provider_phone = _provider_phone(sender.get("phone"))
        supplied_name = _optional(sender.get("display_name"), 255).strip()
        display_name = supplied_name if supplied_name and supplied_name.casefold() != "guest" else (provider_phone or username or "Guest")
        if sender.get("avatar_ref") is not None:
            raise ConnectorPayloadError("unsupported_capability", 422)
        if file_bytes is not None:
            raise ConnectorPayloadError("unsupported_capability", 422)
    elif is_ready:
        if file_bytes is None:
            raise ConnectorPayloadError("unsupported_capability", 422)
        manifest = _object(
            media["manifest"], {"filename", "content_type", "size_bytes", "sha256"},
            {"filename", "content_type", "size_bytes", "sha256"},
        )
        # Use the *existing* M1 verifier. This is an in-process DTO used only
        # for byte/magic/hash validation, not an additional ingest or event.
        validated = parse_media_event({
            "schema": SCHEMA,
            "source_id": source_id,
            "event": {
                "id": event_id, "type": "message.created",
                "occurred_at": event["occurred_at"],
            },
            "conversation": {"external_chat_id": chat_id},
            "sender": {"external_user_id": "staged-media-validator"},
            "message": {
                "external_message_id": external_message_id,
                "direction": "inbound", "origin": "external_observed",
                "actor": "contact", "kind": "file", "text": "",
                "attachments": [manifest],
            },
        }, bytes_content=file_bytes, filename=filename, content_type=content_type)
        attachment = validated.inbound.files[0]
        digest = manifest["sha256"]
        filename = attachment.name
        content_type = attachment.content_type
    else:
        if file_bytes is not None:
            raise ConnectorPayloadError("unsupported_capability", 422)
        reason = media["reason"]
        retryable = media["retryable"]
        if not isinstance(reason, str) or reason not in FAILURE_REASONS or type(retryable) is not bool:
            raise ConnectorPayloadError("invalid_payload", 400)

    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return LifecycleEvent(
        source_id=source_id, event_id=event_id, event_type=event_type,
        chat_id=chat_id, external_message_id=external_message_id,
        fingerprint=hashlib.sha256(canonical).hexdigest(),
        kind=kind, caption=caption, duration_seconds=duration_seconds,
        part_index=part_index,
        sender_id=sender_id,
        display_name=display_name, username=username, provider_phone=provider_phone,
        reason=reason, retryable=retryable,
        file_bytes=file_bytes or b"", filename=filename,
        content_type=content_type, sha256=digest,
    )
