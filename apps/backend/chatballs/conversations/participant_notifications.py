"""Public specialist notice, separate from the internal participation journal."""

from chatballs.conversations import transports
from chatballs.conversations.models import ConnectionIdentity, Message, MessageAuthor, SystemEvent
from chatballs.events.handlers import register
from chatballs.events.services import DomainEvent, enqueue_event
from chatballs.i18n import customer_language, t
from chatballs.tenancy.context import TenantContext

SPECIALIST_NOTICE_REQUESTED = "conversations.specialist_notice_requested"
_DELIVERED = "specialist_notice:delivered"


def queue_specialist_notice(*, conversation, participant, context):
    from chatballs.conversations.services import operator_label

    message = Message.objects.create(
        conversation=conversation, author_type=MessageAuthor.SYSTEM,
        system_event=SystemEvent.SPECIALIST_JOINED,
        system_params={"operator": operator_label(participant.membership.user)}, text="",
    )
    if conversation.connection_id:
        # The committed fact belongs to the organization, so later blocking the
        # initiator must not prevent delivery. No internal reason enters outbox.
        enqueue_event(DomainEvent(
            aggregate_type="Conversation", aggregate_id=str(conversation.pk),
            event_type=SPECIALIST_NOTICE_REQUESTED, payload={"messageId": message.pk},
            tenant_context=TenantContext.for_resource(
                context.organization, correlation_id=context.correlation_id,
            ),
        ))
    return message


def customer_message_text(message):
    if message.system_event != SystemEvent.SPECIALIST_JOINED:
        return message.text
    return t(
        "conversations.system.specialist_joined",
        language=customer_language(message.conversation.organization),
        operator=message.system_params["operator"],
    )


@register(SPECIALIST_NOTICE_REQUESTED)
def deliver_specialist_notice(payload, context):
    if context is None:
        return
    # The handler transaction locks this message, preventing simultaneous retry
    # delivery. Missing/deleted messages and foreign payloads are ignored.
    message = Message.objects.select_for_update().filter(
        pk=payload.get("messageId"), organization_id=context.organization_id,
        system_event=SystemEvent.SPECIALIST_JOINED, author_type=MessageAuthor.SYSTEM,
    ).first()
    if message is None or message.external_id == _DELIVERED:
        return
    conversation = message.conversation
    if not conversation.connection_id:
        return
    identity = ConnectionIdentity.objects.filter(
        connection=conversation.connection, contact=conversation.contact,
    ).first()
    sent = transports.send_reply(
        conversation.connection, chat_id=conversation.external_chat_id,
        user_id=identity.external_user_id if identity else "",
        text=customer_message_text(message),
    )
    if not sent:
        raise RuntimeError("Specialist notice delivery failed")
    message.external_id = _DELIVERED
    message.save(update_fields=["external_id"])
