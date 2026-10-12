"""Persist an employee response and deliver through the existing transport."""

from django.db import transaction
from django.utils import timezone

from chatballs.conversations import transports
from chatballs.conversations.access import require_conversation_action
from chatballs.conversations.models import (
    ConnectionIdentity,
    Conversation,
    ExpectedResponder,
    Message,
    MessageAuthor,
)
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


def post_operator_message(
    *, context: TenantContext, conversation: Conversation, text: str,
    defer_delivery: bool = False,
) -> Message:
    from chatballs.conversations.services import _require_open

    operator = context.actor_user
    if operator is None or conversation.organization_id != context.organization_id:
        raise Conversation.DoesNotExist
    require_conversation_action(context, conversation, "conversations.operate")
    _require_open(conversation)
    message = Message.objects.create(
        conversation=conversation, author_type=MessageAuthor.OPERATOR,
        author_user=operator, text=text,
    )
    conversation.last_activity_at = timezone.now()
    conversation.expected_responder = ExpectedResponder.CUSTOMER
    conversation.save(update_fields=["last_activity_at", "expected_responder"])
    if conversation.connection_id:
        identity = ConnectionIdentity.objects.filter(
            connection=conversation.connection, contact=conversation.contact,
        ).first()
        connection = conversation.connection
        chat_id = conversation.external_chat_id
        user_id = identity.external_user_id if identity else ""

        def deliver():
            # Legacy email delivery reads thread metadata and organization language.
            # After commit there is no ambient tenant scope; restore it per operation.
            with tenant_atomic(context):
                transports.send_reply(connection, chat_id=chat_id, user_id=user_id, text=text)

        if defer_delivery:
            transaction.on_commit(deliver)
        else:
            deliver()
    return message
