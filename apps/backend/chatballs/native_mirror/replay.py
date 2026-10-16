"""Durable replay of staged native events through the canonical accept()."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from chatballs.native_mirror.classification import OriginClass
from chatballs.native_mirror.contracts import MirrorOutcome, MirrorResult, NativeReplyEvent
from chatballs.native_mirror.models import MirrorReceiptStatus, NativeMirrorReceipt
from chatballs.native_mirror.service import NativeMirrorRejected, accept_native_reply
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic

logger = logging.getLogger(__name__)

REPLAY_BATCH_LIMIT = 50
REPLAY_LEASE_SECONDS = 300
RETRY_BASE_SECONDS = 15
RETRY_MAX_SECONDS = 1800


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


def _schedule_retry(*, receipt_id: int, prior_attempts: int,
                    context: TenantContext) -> None:
    with tenant_atomic(context):
        pending = NativeMirrorReceipt.objects.select_for_update(of=("self",)).filter(
            id=receipt_id,
            organization_id=context.organization_id,
            status=MirrorReceiptStatus.PENDING,
        ).first()
        if pending is None:
            return
        # Count attempts that failed before the canonical accept path could
        # update the receipt (for example, revoked authorization).
        if pending.attempts <= prior_attempts:
            pending.attempts = prior_attempts + 1
        exponent = min(max(pending.attempts - 1, 0), 7)
        delay = min(RETRY_BASE_SECONDS * (2 ** exponent), RETRY_MAX_SECONDS)
        pending.next_attempt_at = timezone.now() + timedelta(seconds=delay)
        pending.save(update_fields=["attempts", "next_attempt_at"])
        if delay == RETRY_MAX_SECONDS:
            logger.warning(
                "Native Mirror receipt remains pending receipt=%s reason=%s attempts=%s retry_in=%s",
                pending.id, pending.reason, pending.attempts, delay,
            )


def replay_due_pending_receipts(*, context: TenantContext,
                                limit: int = REPLAY_BATCH_LIMIT) -> int:
    """Claim and replay one bounded batch without holding locks across items.

    The persisted lease makes work recoverable after a process restart. Rows
    remain PENDING on ambiguous/missing conversations or transient failures.
    """
    batch_size = min(max(int(limit), 0), REPLAY_BATCH_LIMIT)
    if batch_size == 0:
        return 0

    now = timezone.now()
    with tenant_atomic(context):
        receipts = list(
            NativeMirrorReceipt.objects.select_for_update(
                of=("self",), skip_locked=True,
            ).filter(
                organization_id=context.organization_id,
                status=MirrorReceiptStatus.PENDING,
                next_attempt_at__lte=now,
            ).order_by("next_attempt_at", "id")[:batch_size]
        )
        for receipt in receipts:
            receipt.next_attempt_at = now + timedelta(seconds=REPLAY_LEASE_SECONDS)
        if receipts:
            NativeMirrorReceipt.objects.bulk_update(receipts, ["next_attempt_at"])

    for claimed in receipts:
        try:
            result = replay_pending_receipt(
                receipt_id=claimed.id, context=context,
            )
        except Exception:
            _schedule_retry(
                receipt_id=claimed.id, prior_attempts=claimed.attempts,
                context=context,
            )
            logger.exception("Native Mirror replay failed receipt=%s", claimed.id)
            continue

        _schedule_retry(
            receipt_id=claimed.id, prior_attempts=claimed.attempts,
            context=context,
        )
        logger.info(
            "Native Mirror replay receipt=%s outcome=%s retryable=%s",
            claimed.id, result.outcome, result.retryable,
        )

    return len(receipts)
