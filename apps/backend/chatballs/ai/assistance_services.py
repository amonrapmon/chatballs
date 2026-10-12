"""Request/reject assistance without changing conversation control or messages."""

from django.db import connection, transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from chatballs.ai.assistance_access import reply_context
from chatballs.ai.assistance_history import history_snapshot
from chatballs.ai.assistance_realtime import notify_suggestion
from chatballs.ai.models import (
    ReplyAssistanceAttempt,
    ReplyAssistanceStatus,
    ReplySuggestion,
)
from chatballs.events.services import DomainEvent, enqueue_event
from chatballs.i18n import t
from chatballs.tenancy.context import TenantContext

ASSISTANCE_REQUESTED = "conversation.reply_assistance_requested"


def lock_operation(context, key):
    # Tenant-wide keys can race across different conversations.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                       [f"assistance:{context.organization_id}:{key}"])


def operation_key(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise ValidationError({"operationKey": t("ai.assistance.invalid_key")})
    return value.strip()


def attempt_for(context, conversation, public_id):
    attempt = ReplyAssistanceAttempt.objects.filter(
        organization_id=context.organization_id, conversation=conversation, public_id=public_id,
    ).first()
    if attempt is None:
        raise NotFound(t("conversations.not_found"))
    return attempt


@transaction.atomic
def request_suggestion(*, context, conversation_id, key, attempt_id=None):
    key = operation_key(key)
    lock_operation(context, key)
    member, conversation = reply_context(context, conversation_id)
    attempt = attempt_for(context, conversation, attempt_id) if attempt_id else None
    existing = ReplySuggestion.objects.filter(
        organization_id=context.organization_id, operation_key=key,
    ).select_related("attempt").first()
    if existing:
        if (existing.attempt.conversation_id != conversation.pk
                or existing.requested_by_id != member.pk
                or (attempt and existing.attempt_id != attempt.pk)
                or (not attempt and existing.position != 1)):
            raise ValidationError(t("ai.assistance.key_conflict"))
        return existing
    agent = getattr(conversation.channel, "ai_agent", None)
    if agent is None or not agent.assistance_enabled:
        raise ValidationError(t("ai.assistance.disabled"))
    if attempt and (attempt.agent_id != agent.pk or attempt.status != ReplyAssistanceStatus.READY):
        raise ValidationError(t("ai.assistance.not_ready"))
    _, _, version = history_snapshot(conversation, agent.history_limit)
    if attempt is None:
        if ReplyAssistanceAttempt.objects.filter(
            organization_id=context.organization_id, operation_key=key,
        ).exists():
            raise ValidationError(t("ai.assistance.key_conflict"))
        attempt = ReplyAssistanceAttempt.objects.create(
            organization=context.organization, conversation=conversation, agent=agent,
            requested_by=member, operation_key=key, history_version=version,
        )
    position = (attempt.suggestions.aggregate(value=Max("position"))["value"] or 0) + 1
    suggestion = ReplySuggestion.objects.create(
        organization=context.organization, attempt=attempt, position=position,
        requested_by=member, operation_key=key, history_version=version,
    )
    # A machine-owned event still revalidates the original requester. Blocking
    # the requester must produce a safe terminal result, not an undeliverable event.
    enqueue_event(DomainEvent(
        aggregate_type="ReplyAssistance", aggregate_id=str(conversation.pk),
        event_type=ASSISTANCE_REQUESTED, payload={"suggestionId": str(suggestion.public_id)},
        tenant_context=TenantContext.for_resource(context.organization),
    ))
    notify_suggestion(suggestion)
    return suggestion


@transaction.atomic
def reject_suggestion(*, context, conversation_id, suggestion_id):
    member, conversation = reply_context(context, conversation_id)
    suggestion = ReplySuggestion.objects.select_for_update().filter(
        organization_id=context.organization_id, attempt__conversation=conversation,
        public_id=suggestion_id,
    ).first()
    if suggestion is None:
        raise NotFound(t("conversations.not_found"))
    if suggestion.status != ReplyAssistanceStatus.READY:
        raise ValidationError(t("ai.assistance.not_ready"))
    from chatballs.ai.assistance_send_models import ReplySuggestionSend

    if ReplySuggestionSend.objects.filter(suggestion=suggestion).exists():
        raise ValidationError(t("ai.assistance.not_ready"))
    if suggestion.rejected_at is None:
        suggestion.rejected_by = member
        suggestion.rejected_at = timezone.now()
        suggestion.save(update_fields=["rejected_by", "rejected_at"])
        notify_suggestion(suggestion)
    return suggestion
