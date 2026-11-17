"""Provider-neutral, identity-scoped avatar ingestion through Connector multipart v1.

Adapters fetch remote images themselves. Chatballs never follows provider URLs.
Only known identities may change; no phantom Contacts, Messages or verified phones.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from django.db import transaction

from chatballs.api_connector.media_validation import verify_media
from chatballs.api_connector.payloads import (
    ConnectorPayloadError,
    _identifier,
    _object,
    _utc_timestamp,
)
from chatballs.conversations.contact_avatars import MAX_AVATAR_BYTES, store_contact_avatar
from chatballs.conversations.inbound_dedup import _already_processed
from chatballs.conversations.models import ConnectionIdentity
from chatballs.identity.avatars import image_type
from chatballs.tenancy.context import TenantContext


@dataclass(frozen=True)
class AvatarProfileEvent:
    source_id: str
    event_id: str
    fingerprint: str
    external_user_id: str
    content: bytes
    digest: str


def parse_avatar_event(
    payload: object, *, file_bytes: bytes, filename: str, content_type: str,
) -> AvatarProfileEvent:
    body = _object(
        payload, {"schema", "source_id", "event", "profile", "avatar"},
        {"schema", "source_id", "event", "profile", "avatar"},
    )
    if body["schema"] != "chatballs.api-connector.event.v1":
        raise ConnectorPayloadError("unsupported_schema", 422)
    source_id = _identifier(body["source_id"], 128)
    event = _object(body["event"], {"id", "type", "occurred_at"}, {"id", "type", "occurred_at"})
    event_id = _identifier(event["id"], 256)
    if event["type"] != "contact.avatar.updated":
        raise ConnectorPayloadError("unsupported_event_type", 422)
    _utc_timestamp(event["occurred_at"])
    profile = _object(body["profile"], {"external_user_id"}, {"external_user_id"})
    user_id = _identifier(profile["external_user_id"], 128)
    avatar = _object(
        body["avatar"],
        {"filename", "content_type", "size_bytes", "sha256"},
        {"filename", "content_type", "size_bytes", "sha256"},
    )
    if type(avatar["size_bytes"]) is not int or not 0 < avatar["size_bytes"] <= MAX_AVATAR_BYTES:
        raise ConnectorPayloadError("invalid_media", 400)
    try:
        verify_media(
            content=file_bytes, filename=avatar["filename"],
            content_type=avatar["content_type"], size=avatar["size_bytes"],
            sha256=avatar["sha256"], uploaded_name=filename,
            uploaded_mime=content_type, kind="image",
        )
    except ValueError as error:
        raise ConnectorPayloadError("invalid_media", 400) from error
    # The native contact-avatar store accepts JPEG, PNG and WebP only.
    if image_type(file_bytes) is None:
        raise ConnectorPayloadError("invalid_media", 400)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return AvatarProfileEvent(
        source_id, event_id, hashlib.sha256(encoded).hexdigest(),
        user_id, file_bytes, avatar["sha256"],
    )


@transaction.atomic
def apply_avatar_event(integration, event: AvatarProfileEvent) -> None:
    if event.source_id != f"connection-{integration.pk}":
        raise ConnectorPayloadError("source_mismatch", 409)
    try:
        duplicate = _already_processed(
            TenantContext.for_resource(integration.organization),
            f"api_connector:{integration.pk}", event.event_id, "",
            payload_hash=event.fingerprint,
        )
    except ValueError as error:
        if str(error) == "connector_event_id_conflict":
            raise ConnectorPayloadError("id_conflict", 409) from error
        raise
    if duplicate:
        return
    identity = (
        ConnectionIdentity.objects.select_for_update().select_related("contact")
        .filter(connection=integration, external_user_id=event.external_user_id)
        .first()
    )
    if identity is None:
        return
    contact = identity.contact
    source_prefix = f"connector:{integration.pk}:"
    # Do not override a manually-provided avatar or another integration's photo.
    if contact.avatar and not contact.avatar_source.startswith(source_prefix):
        return
    source = f"{source_prefix}{event.digest}"
    if contact.avatar and contact.avatar_source == source:
        return
    if not store_contact_avatar(contact, content=event.content, source=source):
        raise ConnectorPayloadError("invalid_media", 400)
