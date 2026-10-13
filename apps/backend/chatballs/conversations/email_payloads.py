"""Safe staff-facing operation and attempt representations."""

from chatballs.conversations.email_continuation import require_reply, retry_allowed
from chatballs.conversations.email_options import letter_mailbox_available
from chatballs.conversations.models import Conversation
from chatballs.conversations.services import ClaimError
from chatballs.i18n import t


def attempt_payload(attempt):
    reason = {
        "CONNECTION_UNAVAILABLE": "conversations.email_connection_unavailable",
        "SMTP_REJECTED": "conversations.email_smtp_rejected",
        "TRANSPORT_ERROR": "conversations.email_send_interrupted" if attempt.state == "UNKNOWN" else "conversations.email_connect_failed",
        "WORKER_INTERRUPTED": "conversations.email_worker_interrupted",
    }.get(attempt.error_code)
    return {
        "id": attempt.pk, "number": attempt.number, "state": attempt.state,
        "initiatedById": attempt.initiated_by.user_id, "errorCode": attempt.error_code,
        "initiatedByName": attempt.initiated_by.user.full_name or attempt.initiated_by.user.email,
        "errorMessage": t(reason) if reason else "",
        "createdAt": attempt.created_at.isoformat(),
        "startedAt": attempt.started_at.isoformat() if attempt.started_at else None,
        "finishedAt": attempt.finished_at.isoformat() if attempt.finished_at else None,
    }


def operation_payload(operation, *, context=None):
    letter = operation.letter
    allowed = retry_allowed(operation) and letter_mailbox_available(letter)
    if context is not None and allowed:
        try:
            require_reply(context, letter.thread.conversation)
        except (Conversation.DoesNotExist, ClaimError):
            allowed = False
    return {
        "id": operation.pk, "messageId": letter.message_id, "threadId": letter.thread_id,
        "mailMessageId": letter.mail_message_id, "connectionId": letter.connection_id,
        "recipient": letter.thread.recipient, "subject": letter.thread.subject,
        "senderAddress": letter.sender_address or None, "mailboxName": letter.mailbox_name or None,
        "initiatedById": operation.initiated_by.user_id, "createdAt": operation.created_at.isoformat(),
        "retryAllowed": allowed, "deliveryConfirmed": False,
        "attempts": [attempt_payload(attempt) for attempt in operation.attempts.select_related("initiated_by__user").all()],
    }
