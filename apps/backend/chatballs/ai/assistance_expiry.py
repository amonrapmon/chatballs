"""Expire abandoned operations on protected reads, without calling the model."""

from chatballs.ai.assistance_generation import finish, time_left
from chatballs.ai.assistance_models import ReplyAssistanceError
from chatballs.ai.models import ReplyAssistanceStatus


def expire_attempt(attempt):
    # Caller holds the conversation lock in the tenant transaction.
    for suggestion in attempt.suggestions.select_for_update().filter(
        status__in=(ReplyAssistanceStatus.PENDING, ReplyAssistanceStatus.RUNNING),
    ):
        if time_left(suggestion) <= 0:
            finish(suggestion, error=ReplyAssistanceError.TIMEOUT)
    attempt.refresh_from_db()
    return attempt
