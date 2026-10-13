"""Writers used by communication services, inside their domain transaction."""

from uuid import NAMESPACE_URL, uuid4, uuid5

from rest_framework.exceptions import ValidationError

from chatballs.conversations.domain_event_models import (
    ConversationEvent,
    ConversationEventActor,
    ConversationEventType,
)
from chatballs.conversations.models import Conversation
from chatballs.i18n import t

_CURRENT_RESPONSIBLE = object()


def is_accepted(conversation):
    if conversation.control_mode != "HUMAN":
        return False
    latest = conversation.domain_events.filter(
        event_type__in={"ACCEPTED", "ASSIGNED", "TRANSFERRED", "QUEUE_ENTERED", "CLOSED"},
    ).order_by("-sequence").first()
    if latest is None:
        # Existing HUMAN conversations keep their behavior; missing history
        # must not fabricate a new acceptance on the next ordinary reply.
        return conversation.assigned_operator_id is not None
    return bool(latest.event_type == "ACCEPTED"
                and latest.responsible_id == conversation.assigned_operator_id)


def operation_key(source, identifier):
    return uuid5(NAMESPACE_URL, f"chatballs:{source}:{identifier}")


def record_fact(conversation, event_type, *, operation_id=None,
                actor_kind=ConversationEventActor.SYSTEM, initiated_by_id=None,
                responsible_id=_CURRENT_RESPONSIBLE, connection=None):
    connection = connection or conversation.connection
    current = Conversation.objects.select_for_update().get(
        pk=conversation.pk, organization_id=conversation.organization_id,
    )
    if responsible_id is _CURRENT_RESPONSIBLE:
        responsible_id = current.assigned_operator_id
    event = ConversationEvent.objects.get_or_create(
        organization_id=conversation.organization_id,
        operation_id=operation_id or uuid4(), event_type=event_type,
        defaults={
            "conversation": conversation, "actor_kind": actor_kind,
            "initiated_by_id": initiated_by_id,
            "responsible_id": responsible_id,
            "group_id": current.group_id,
            "connection_id": connection.pk if connection else None,
            "transport": connection.provider if connection else None,
        },
    )[0]
    if event.conversation_id != conversation.pk or event.actor_kind != actor_kind:
        raise ValidationError(t("transfers.operation_invalid"))
    if event_type == ConversationEventType.CLOSED:
        from chatballs.conversations.quality.queue import schedule_completion

        schedule_completion(current, event)
    return event


def record_public_reply(message, *, operation_id=None):
    conversation = message.conversation
    return record_fact(
        conversation, ConversationEventType.PUBLIC_REPLY,
        operation_id=operation_id or operation_key("reply", message.pk),
        actor_kind=(ConversationEventActor.HUMAN if message.author_type == "OPERATOR"
                    else ConversationEventActor.AI),
        initiated_by_id=message.author_user_id,
    )


def record_queue_entry(conversation, *, entered, operation_id=None,
                       actor_kind=ConversationEventActor.SYSTEM, connection=None):
    if entered:
        record_fact(
            conversation, ConversationEventType.QUEUE_ENTERED,
            operation_id=operation_id, actor_kind=actor_kind, connection=connection,
        )
