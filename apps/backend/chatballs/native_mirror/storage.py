"""Provider-event deduplication and durable staged payload storage.

Must be used inside a tenant transaction. Conversation row, when present,
must be locked before entering these helpers.
"""

from __future__ import annotations

import hashlib

from django.db import IntegrityError, transaction

from chatballs.native_mirror.contracts import NativeReplyEvent
from chatballs.native_mirror.models import NativeMirrorReceipt


class NativeMirrorConflict(ValueError):
    """Same provider identity was reused with different event content."""


def _fingerprint(event: NativeReplyEvent) -> str:
    parts = (
        event.provider, event.source_id, event.external_chat_id,
        event.external_message_id, event.occurred_at.isoformat(),
        event.external_reply_to_id, event.text,
    )
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def stage_event(*, event: NativeReplyEvent, organization_id: int,
                author_user_id: int | None) -> tuple[NativeMirrorReceipt, bool]:
    """Get or insert a locked receipt. True means provider ID had another event ID.

    The database unique constraints are the final authority. If two workers
    insert at once, recover after rolling back only the failed savepoint.
    """
    fingerprint = _fingerprint(event)
    query = NativeMirrorReceipt.objects.select_for_update().filter(
        integration_id=event.integration_id
    )
    receipt = query.filter(event_id=event.event_id).first()
    alternative = False
    if receipt is None:
        receipt = query.filter(
            external_chat_id=event.external_chat_id,
            external_message_id=event.external_message_id,
        ).first()
        alternative = receipt is not None
    if receipt is None:
        try:
            with transaction.atomic():
                receipt = NativeMirrorReceipt.objects.create(
                    organization_id=organization_id,
                    integration_id=event.integration_id,
                    event_id=event.event_id,
                    external_chat_id=event.external_chat_id,
                    external_message_id=event.external_message_id,
                    payload_hash=fingerprint,
                    occurred_at=event.occurred_at,
                    external_reply_to_id=event.external_reply_to_id,
                    pending_text=event.text,
                    author_user_id=author_user_id,
                )
        except IntegrityError:
            receipt = query.filter(event_id=event.event_id).first()
            if receipt is None:
                receipt = query.get(
                    external_chat_id=event.external_chat_id,
                    external_message_id=event.external_message_id,
                )
                alternative = True

    if receipt.payload_hash != fingerprint:
        raise NativeMirrorConflict(
            "Conflicting payload for an existing native provider event/message ID"
        )
    if receipt.author_user_id is not None and (
        author_user_id is not None and receipt.author_user_id != author_user_id
    ):
        raise NativeMirrorConflict("Native provider event changed verified author")
    return receipt, alternative
