"""Apply staged Connector media to a single native Message.

The adapter never supplies a public media URL. This service never sends a
provider message; it only changes inbound media already announced by a trusted,
Integration-scoped event.
"""
from __future__ import annotations

import hashlib

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction

from chatballs.api_connector.lifecycle import MEDIA_KINDS, LifecycleEvent
from chatballs.api_connector.media_validation import verify_media
from chatballs.api_connector.payloads import ConnectorPayloadError
from chatballs.conversations.connector_media_models import ConnectorMediaIngest
from chatballs.conversations.inbound_dedup import _already_processed
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import Message, MessageKind
from chatballs.conversations.transports.base import InboundMessage
from chatballs.tenancy.context import TenantContext

EVENT_SOURCE = "api_connector:{id}"


def _conflict(code: str) -> None:
    raise ConnectorPayloadError(code, 409)


def _read_media_row(integration, event: LifecycleEvent):
    return (
        ConnectorMediaIngest.objects.select_for_update()
        .select_related("message")
        .filter(
            organization_id=integration.organization_id,
            integration=integration,
            external_chat_id=event.chat_id,
            external_message_id=event.external_message_id,
            part_index=event.part_index,
        )
        .first()
    )


@transaction.atomic
def apply_media_lifecycle(integration, event: LifecycleEvent) -> None:
    if event.source_id != f"connection-{integration.pk}":
        _conflict("source_mismatch")
    if integration.config.get("connectorMediaLifecycleEnabled") is not True:
        raise ConnectorPayloadError("unsupported_capability", 422)

    source = EVENT_SOURCE.format(id=integration.pk)
    row = _read_media_row(integration, event)
    if event.event_type == "message.media.announced":
        if row:
            if (row.announce_event_id != event.event_id
                    or row.announce_fingerprint != event.fingerprint):
                _conflict("media_identity_conflict")
            return

        # A root already owned by a one-shot file/observed message cannot
        # also be used for staged parts. A staged part zero establishes root
        # ownership, and subsequent parts are independently identified.
        root_message_exists = Message.objects.filter(
            conversation__connection=integration,
            conversation__external_chat_id=event.chat_id,
            external_id=event.external_message_id,
        ).exists()
        root_owned_by_media = ConnectorMediaIngest.objects.filter(
            organization_id=integration.organization_id,
            integration=integration, external_chat_id=event.chat_id,
            external_message_id=event.external_message_id,
            part_index=0,
        ).exists()
        if root_message_exists and (event.part_index == 0 or not root_owned_by_media):
            _conflict("media_identity_conflict")

        # Message.external_id stays a stable <=128-character per-part value;
        # ConnectorMediaIngest stores the authoritative provider root.
        part_message_id = (
            event.external_message_id if event.part_index == 0
            else "part:" + hashlib.sha256(
                f"{event.external_message_id}:{event.part_index}".encode("utf-8")
            ).hexdigest()
        )
        inbound = InboundMessage(
            external_id=part_message_id,
            user_id=event.sender_id,
            chat_id=event.chat_id,
            display_name=event.display_name,
            username=event.username,
            provider_phone=event.provider_phone,
            text=event.caption,
        )
        try:
            ingest_inbound(
                integration, inbound, connector_event_id=event.event_id,
                connector_fingerprint=event.fingerprint,
                connector_media_announcement={
                    "kind": event.kind, "duration_seconds": event.duration_seconds,
                    "root_id": event.external_message_id, "part_index": event.part_index,
                },
            )
        except IntegrityError:
            _conflict("media_identity_conflict")
        except ValueError as error:
            if str(error) == "connector_event_id_conflict":
                _conflict("id_conflict")
            if str(error) == "connector_media_identity_conflict":
                _conflict("media_identity_conflict")
            raise
        # Cross-family reused event IDs may have been accepted by InboxEvent
        # dedup before a native media row was inserted: never claim success.
        row = _read_media_row(integration, event)
        if not row:
            _conflict("id_conflict")
        if (row.announce_event_id != event.event_id
                or row.announce_fingerprint != event.fingerprint):
            _conflict("media_identity_conflict")
        return

    if row is None:
        # An out-of-order provider callback must not fabricate a conversation.
        _conflict("unknown_media")

    message = row.message
    current = message.connector_media or {}
    if current.get("kind") not in MEDIA_KINDS:
        _conflict("media_identity_conflict")
    if event.event_type == "message.media.ready":
        # A ready callback has no caller-supplied kind; the stored announcement
        # is authoritative for both format checks and the native Message kind.
        try:
            verify_media(
                content=event.file_bytes, filename=event.filename,
                content_type=event.content_type, size=len(event.file_bytes),
                sha256=event.sha256, kind=current["kind"],
            )
        except ValueError as error:
            raise ConnectorPayloadError("invalid_media", 400) from error
        if current.get("status") == "READY" and current.get("sha256") != event.sha256:
            _conflict("media_identity_conflict")

    context = TenantContext.for_resource(integration.organization)
    try:
        duplicate = _already_processed(
            context, source, event.event_id, "",
            payload_hash=event.fingerprint,
        )
    except ValueError as error:
        if str(error) == "connector_event_id_conflict":
            _conflict("id_conflict")
        raise
    if duplicate:
        # The same InboxEvent ID may have been used by a different v1 family.
        # A pending media cannot silently ACK a ready/failed ID it never applied.
        if event.event_type == "message.media.ready" and current.get("status") != "READY":
            _conflict("id_conflict")
        if event.event_type == "message.media.failed" and current.get("status") == "PENDING":
            _conflict("id_conflict")
        return

    if current.get("status") == "READY":
        # Late FAILED cannot regress READY, even from a new provider event ID.
        return

    if event.event_type == "message.media.failed":
        reason = event.reason
        if current.get("status") == "FAILED" and (
            current.get("reason") == reason
            and current.get("retryable") == event.retryable
        ):
            return
        message.connector_media = {
            "status": "FAILED", "kind": current["kind"],
            "reason": reason, "retryable": event.retryable,
            "revision": int(current.get("revision", 1)) + 1,
        }
        message.save(update_fields=["connector_media"])
        return

    # All integrity verification is already done in parse_lifecycle_event.
    # Use the SAME native FieldFile; no staging blob and no provider URL.
    if current.get("status") not in {"PENDING", "FAILED"}:
        _conflict("media_invalid_transition")
    is_voice = current["kind"] == "voice"
    if message.kind != (MessageKind.VOICE if is_voice else MessageKind.FILE):
        _conflict("media_identity_conflict")
    written = ""
    storage = message.audio.storage if is_voice else message.attachment.storage
    try:
        if is_voice:
            message.audio.save(event.filename, ContentFile(event.file_bytes), save=False)
            written = message.audio.name
            message.audio_content_type = event.content_type
            fields = ["audio", "audio_content_type", "connector_media"]
        else:
            message.attachment.save(event.filename, ContentFile(event.file_bytes), save=False)
            written = message.attachment.name
            message.attachment_name = event.filename
            message.attachment_content_type = event.content_type
            message.attachment_size = len(event.file_bytes)
            fields = [
                "attachment", "attachment_name", "attachment_content_type",
                "attachment_size", "connector_media",
            ]
        message.connector_media = {
            "status": "READY", "kind": current["kind"],
            "reason": "", "retryable": False,
            "revision": int(current.get("revision", 1)) + 1,
            "sha256": event.sha256,
        }
        message.save(update_fields=fields)
    except Exception:
        # FieldFile writes precede the DB commit. Compensate immediate failures.
        # Late transaction orphans remain handled by the reconciliation worker.
        if written:
            try:
                storage.delete(written)
            except OSError:
                pass
        raise
