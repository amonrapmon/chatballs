"""Bounded multipart-to-native InboundFile bridge for API Connector.

The adapter owns provider downloads. Chatballs accepts bytes and delegates
message/attachment persistence to the existing conversations ingest service.
"""
from __future__ import annotations

from rest_framework.request import Request

from chatballs.api_connector.payloads import (
    ConnectorPayloadError,
    ParsedTextEvent,
    parse_media_event,
)
from chatballs.conversations.attachment_policy import MAX_FILE_BYTES, validate_upload

# This bounds the entire multipart envelope before Django starts file parsing.
MAX_MULTIPART_BODY_BYTES = MAX_FILE_BYTES + 2 * 64 * 1024
MAX_MEDIA_EVENT_BYTES = 64 * 1024


def parse_multipart_event(request: Request, *, decode_json) -> ParsedTextEvent:
    """Require exactly one JSON event field and one binary file field."""
    data = request.data
    files = request.FILES
    if set(data.keys()) != {"event", "file"} or set(files.keys()) != {"file"}:
        raise ConnectorPayloadError("invalid_payload", 400)
    events = data.getlist("event")
    uploads = files.getlist("file")
    if len(events) != 1 or len(uploads) != 1 or not isinstance(events[0], str):
        raise ConnectorPayloadError("invalid_payload", 400)

    raw = events[0].encode("utf-8")
    if len(raw) > MAX_MEDIA_EVENT_BYTES:
        raise ConnectorPayloadError("payload_too_large", 413)
    try:
        payload = decode_json(raw)
    except (UnicodeError, ValueError):
        raise ConnectorPayloadError("invalid_payload", 400) from None

    upload = uploads[0]
    if upload.size > MAX_FILE_BYTES:
        raise ConnectorPayloadError("payload_too_large", 413)
    if validate_upload(upload):
        raise ConnectorPayloadError("invalid_media", 400)
    length = 0
    chunks: list[bytes] = []
    for chunk in upload.chunks():
        length += len(chunk)
        if length > MAX_FILE_BYTES:
            raise ConnectorPayloadError("payload_too_large", 413)
        chunks.append(chunk)

    return parse_media_event(
        payload,
        bytes_content=b"".join(chunks),
        filename=upload.name,
        content_type=(upload.content_type or "").split(";", 1)[0].lower(),
    )
