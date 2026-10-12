"""Explicit durable replay entry point for previously staged native events.

A future scheduler can call this after restarts without depending on provider
redelivery. The decision and write still go through the canonical accept().
"""

from __future__ import annotations

from chatballs.native_mirror.classification import OriginClass
from chatballs.native_mirror.contracts import MirrorOutcome, MirrorResult, NativeReplyEvent
from chatballs.native_mirror.models import MirrorReceiptStatus, NativeMirrorReceipt
from chatballs.native_mirror.service import NativeMirrorRejected, accept_native_reply
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


def replay_pending_receipt(*, receipt_id: int, context: TenantContext) -> MirrorResult:
    """Reconstruct a previously verified event from durable staging.

    Read in a short transaction, then delegate to accept's own locked
    transaction. A simultaneous provider retry is resolved by the unique
    receipt key, not by this unlocked snapshot.
    """
    with tenant_atomic(context):
        receipt = NativeMirrorReceipt.objects.filter(
            id=receipt_id, organization_id=context.organization_id,
        ).first()
        if receipt is None:
            raise NativeMirrorRejected("Native receipt not found for organization")
        if receipt.status != MirrorReceiptStatus.PENDING:
            return MirrorResult(
                MirrorOutcome.DUPLICATE, message_id=receipt.message_id
            )
        if receipt.author_user_id is None or not receipt.pending_text:
            raise NativeMirrorRejected("Pending native receipt has no verified origin/text")
        event = NativeReplyEvent(
            integration_id=receipt.integration_id,
            provider=receipt.provider,
            source_id=receipt.source_id,
            external_chat_id=receipt.external_chat_id,
            event_id=receipt.event_id,
            external_message_id=receipt.external_message_id,
            occurred_at=receipt.occurred_at,
            text=receipt.pending_text,
            external_reply_to_id=receipt.external_reply_to_id,
        )
        author_user_id = receipt.author_user_id

    return accept_native_reply(
        event=event, context=context, origin=OriginClass.EXTERNAL_AUTHORIZED,
        author_user_id=author_user_id,
    )
