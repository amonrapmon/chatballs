"""Conversation deletion includes private assistance history (SPEC-0018 R-5)."""

from chatballs.ai.models import ReplyAssistanceAttempt, ReplySuggestion


def delete_conversation_assistance(conversation):
    attempts = ReplyAssistanceAttempt.objects.filter(
        organization_id=conversation.organization_id, conversation=conversation,
    )
    ReplySuggestion.objects.filter(attempt__in=attempts).delete()
    attempts.delete()
