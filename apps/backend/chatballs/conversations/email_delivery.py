"""Outbox delivery releases DB locks before SMTP; replay never sends twice."""

from datetime import timedelta

from django.utils import timezone

from chatballs.conversations.email_attempt_models import EmailSendAttempt
from chatballs.conversations.email_continuation import require_reply
from chatballs.conversations.email_options import letter_mailbox_available
from chatballs.conversations.models import Conversation
from chatballs.conversations.services import ClaimError
from chatballs.conversations.transports.email_smtp import (
    MailOutcome,
    continuation_message,
    deliver_message,
)
from chatballs.events.services import PROCESSING_LEASE_SECONDS
from chatballs.identity.models import OrganizationMembership
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


class EmailAttemptInProgress(Exception):
    """Keep a replay in outbox until the sender finishes or its lease expires."""


def finish_attempt(attempt, outcome):
    attempt.state, attempt.error_code = outcome.state, outcome.error_code
    attempt.finished_at = timezone.now()
    attempt.save(update_fields=["state", "error_code", "finished_at"])


def recover_sending_attempt(attempt, *, now=None):
    if attempt.started_at <= (now or timezone.now()) - timedelta(seconds=PROCESSING_LEASE_SECONDS):
        finish_attempt(attempt, MailOutcome("UNKNOWN", "WORKER_INTERRUPTED"))


def begin_attempt(context, payload):
    attempt = EmailSendAttempt.objects.select_for_update(of=("self",)).select_related(
        "operation__letter__thread__conversation", "operation__letter__connection__channel",
        "operation__letter__message",
    ).filter(
        organization_id=context.organization_id, operation_id=payload.get("operation_id"),
        number=payload.get("attempt"),
    ).first()
    if attempt is None:
        return None
    if attempt.state == "SENDING":
        recover_sending_attempt(attempt)
        if attempt.state == "SENDING":
            # The event lease starts before SMTP preparation, so an outbox
            # replay may arrive just before this attempt's own lease expires.
            raise EmailAttemptInProgress("Email attempt is still in progress")
        return None
    if attempt.state != "PENDING":
        return None
    letter = attempt.operation.letter
    actor = OrganizationMembership.objects.select_related("user", "organization").filter(
        pk=attempt.initiated_by_id, organization_id=context.organization_id,
        blocked_at__isnull=True, user__is_active=True,
    ).first()
    conversation = Conversation.objects.select_for_update().get(pk=letter.thread.conversation_id)
    try:
        if actor is None or not letter_mailbox_available(letter) or attempt.operation.attempts.filter(state="SMTP_ACCEPTED").exists():
            raise Conversation.DoesNotExist
        require_reply(TenantContext.for_membership(actor), conversation)
    except (Conversation.DoesNotExist, ClaimError):
        finish_attempt(attempt, MailOutcome("FAILED", "CONNECTION_UNAVAILABLE"))
        return None
    attempt.state, attempt.started_at = "SENDING", timezone.now()
    attempt.save(update_fields=["state", "started_at"])
    return attempt.pk, letter


def deliver_email_reply(payload, context):
    with tenant_atomic(context):
        work = begin_attempt(context, payload)
        if work is None:
            return
        attempt_id, letter = work
        outgoing = continuation_message(letter)
    outcome = deliver_message(letter.connection, outgoing)
    with tenant_atomic(context):
        attempt = EmailSendAttempt.objects.select_for_update().get(pk=attempt_id)
        # A reclaimed lease may already have marked UNKNOWN. An observed final
        # result is stronger evidence, but it must not enable another send.
        if attempt.state in {"SENDING", "UNKNOWN"}:
            finish_attempt(attempt, outcome)
