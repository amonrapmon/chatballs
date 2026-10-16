"""Public mail facts retain the source dimensions and actual EMAIL transport."""

from chatballs.conversations.domain_events import record_fact


def record_email_fact(conversation, connection, *, actor, user_id=None, operation_id=None):
    return record_fact(
        conversation, "PUBLIC_REPLY", operation_id=operation_id,
        actor_kind=actor, initiated_by_id=user_id, connection=connection,
    )
