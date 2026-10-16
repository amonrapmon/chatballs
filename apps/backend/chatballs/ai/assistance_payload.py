"""Protected employee response; never used by the customer history serializers."""

from chatballs.i18n import t


def operation_payload(operation):
    return {
        "id": str(operation.public_id), "status": operation.status,
        "requestedBy": operation.requested_by_id,
        "createdAt": operation.created_at.isoformat(),
        "startedAt": operation.started_at.isoformat() if operation.started_at else None,
        "completedAt": operation.completed_at.isoformat() if operation.completed_at else None,
        "historyVersion": operation.history_version,
        "errorCode": operation.error_code,
        "error": t("ai.assistance.failed") if operation.error_code else "",
    }


def suggestion_payload(suggestion):
    sent = getattr(suggestion, "send", None)
    return {**operation_payload(suggestion), "attemptId": str(suggestion.attempt.public_id),
            "position": suggestion.position, "originalText": suggestion.original_text,
            "rejectedBy": suggestion.rejected_by_id,
            "rejectedAt": suggestion.rejected_at.isoformat() if suggestion.rejected_at else None,
            "sentMessageId": sent.message_id if sent else None,
            "sentBy": sent.sent_by_id if sent else None,
            "sentAt": sent.sent_at.isoformat() if sent else None}


def attempt_payload(attempt):
    return {**operation_payload(attempt),
            "suggestions": [suggestion_payload(s) for s in attempt.suggestions.all()]}
