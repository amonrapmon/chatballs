"""Safe staff-facing operation and attempt representations."""

from chatballs.conversations.email_continuation import require_reply, retry_allowed
from chatballs.conversations.email_options import mailbox_available
from chatballs.conversations.models import Conversation
from chatballs.conversations.services import ClaimError


def attempt_payload(attempt):
    return {
        "id": attempt.pk, "number": attempt.number, "state": attempt.state,
        "initiatedById": attempt.initiated_by.user_id, "errorCode": attempt.error_code,
        "createdAt": attempt.created_at.isoformat(),
        "startedAt": attempt.started_at.isoformat() if attempt.started_at else None,
        "finishedAt": attempt.finished_at.isoformat() if attempt.finished_at else None,
    }


def operation_payload(operation, *, context=None):
    letter = operation.letter
    allowed = retry_allowed(operation) and mailbox_available(letter.connection)
    if context is not None and allowed:
        try:
            require_reply(context, letter.thread.conversation)
        except (Conversation.DoesNotExist, ClaimError):
            allowed = False
    return {
        "id": operation.pk, "messageId": letter.message_id, "threadId": letter.thread_id,
        "mailMessageId": letter.mail_message_id, "connectionId": letter.connection_id,
        "recipient": letter.thread.recipient, "subject": letter.thread.subject,
        "initiatedById": operation.initiated_by.user_id, "createdAt": operation.created_at.isoformat(),
        "retryAllowed": allowed, "deliveryConfirmed": False,
        "attempts": [attempt_payload(attempt) for attempt in operation.attempts.select_related("initiated_by").all()],
    }
