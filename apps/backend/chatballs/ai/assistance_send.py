"""Atomic manual send and durable idempotency, preserving the AI source."""

from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from chatballs.ai.assistance_access import reply_context
from chatballs.ai.assistance_send_models import ReplySuggestionSend
from chatballs.ai.assistance_services import lock_operation, operation_key
from chatballs.ai.models import ReplyAssistanceStatus, ReplySuggestion
from chatballs.conversations.domain_events import is_accepted
from chatballs.conversations.models import ControlMode
from chatballs.conversations.services import (
    claim_locked_conversation,
    post_operator_message,
)
from chatballs.i18n import t


@transaction.atomic
def send_suggestion(*, context, conversation_id, suggestion_id, key, text):
    key = operation_key(key)
    lock_operation(context, "send:" + key)
    member, conversation = reply_context(context, conversation_id)
    suggestion = ReplySuggestion.objects.select_for_update().filter(
        organization_id=context.organization_id, public_id=suggestion_id,
        attempt__conversation=conversation,
    ).first()
    if suggestion is None:
        raise NotFound(t("conversations.not_found"))
    existing = ReplySuggestionSend.objects.select_related("message").filter(
        organization_id=context.organization_id, operation_key=key,
    ).first()
    if existing:
        if (existing.suggestion_id != suggestion.pk or existing.sent_by_id != member.pk
                or existing.message.text != text):
            raise ValidationError(t("ai.assistance.key_conflict"))
        return existing.message
    if (suggestion.status != ReplyAssistanceStatus.READY or suggestion.rejected_at
            or ReplySuggestionSend.objects.filter(suggestion=suggestion).exists()):
        raise ValidationError(t("ai.assistance.not_ready"))
    if conversation.control_mode != ControlMode.HUMAN or (
        conversation.assigned_operator_id == context.actor_user.pk and not is_accepted(conversation)
    ):
        conversation = claim_locked_conversation(context=context, conversation=conversation)
    message = post_operator_message(context=context, conversation=conversation, text=text,
                                    defer_delivery=True)
    ReplySuggestionSend.objects.create(
        organization=context.organization, suggestion=suggestion, message=message,
        sent_by=member, operation_key=key,
    )
    return message
