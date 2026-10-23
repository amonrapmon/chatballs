"""Persist an employee response and deliver through the existing transport."""

from django.db import transaction
from django.utils import timezone

from chatballs.api_connector.outbound import queue_operator_text
from chatballs.conversations import transports
from chatballs.conversations.domain_operations import domain_operation
from chatballs.conversations.models import (
    ConnectionIdentity,
    Conversation,
    ExpectedResponder,
    Message,
    MessageAuthor,
)
from chatballs.conversations.reply_access import require_human_reply
from chatballs.integrations.models import IntegrationProvider
from chatballs.conversations.template_send_guard import require_filled_text
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


def _require_operator_reply(*, context, conversation, text, defer_delivery=False):
    require_filled_text(text)
    require_human_reply(context=context, conversation=conversation)


@domain_operation("PUBLIC_REPLY", guard=_require_operator_reply)
def post_operator_message(
    *, context: TenantContext, conversation: Conversation, text: str,
    defer_delivery: bool = False,
) -> Message:
    operator = context.actor_user
    if operator is None or conversation.organization_id != context.organization_id:
        raise Conversation.DoesNotExist
    message = Message.objects.create(
        conversation=conversation, author_type=MessageAuthor.OPERATOR,
        author_user=operator, text=text,
    )
    conversation.last_activity_at = timezone.now()
    conversation.expected_responder = ExpectedResponder.CUSTOMER
    conversation.save(update_fields=["last_activity_at", "expected_responder"])
    if (conversation.connection_id and
            conversation.connection.provider == IntegrationProvider.API_CONNECTOR):
        queue_operator_text(context=context, conversation=conversation, message=message)
    elif conversation.connection_id:
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
