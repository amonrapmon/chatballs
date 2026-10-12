from django.utils import timezone

from chatballs.conversations import transports
from chatballs.conversations.access import require_conversation_action
from chatballs.conversations.assignment import assign_operator  # noqa: F401
from chatballs.conversations.control_services import (  # noqa: F401
    ClaimError,
    _require_open,
    claim_conversation,
    claim_locked_conversation,
    operator_label,
    release_to_ai,
    return_to_queue,
)
from chatballs.conversations.lifecycle_services import (  # noqa: F401
    close_conversation,
    delete_conversation,
    mark_conversation_as_spam,
)
from chatballs.conversations.models import (
    ConnectionIdentity,
    Conversation,
    ExpectedResponder,
    Message,
    MessageAuthor,
    MessageKind,
)
from chatballs.conversations.operator_messages import (
    post_operator_message as post_operator_message,
)
from chatballs.i18n import customer_language, t
from chatballs.integrations.models import IntegrationProvider
from chatballs.tenancy.context import TenantContext


def request_contact(*, context: TenantContext, conversation: Conversation) -> Message:
    """Запрос контакта у клиента: TG/MAX — сообщение с кнопкой «Поделиться
    контактом», Web — виджет рисует форму телефона по kind=contact_request."""
    operator = context.actor_user
    if operator is None or conversation.organization_id != context.organization_id:
        raise Conversation.DoesNotExist
    require_conversation_action(context, conversation, "conversations.operate")
    _require_open(conversation)
    is_web = conversation.connection_id and conversation.connection.provider == IntegrationProvider.WEB
    key = "conversations.contact_request_web" if is_web else "conversations.contact_request"
    text = t(key, language=customer_language(conversation.organization))
    message = Message.objects.create(
        conversation=conversation,
        author_type=MessageAuthor.OPERATOR,
        author_user=operator,
        kind=MessageKind.CONTACT_REQUEST,
        text=text,
    )
    conversation.last_activity_at = timezone.now()
    conversation.expected_responder = ExpectedResponder.CUSTOMER
    conversation.save(update_fields=["last_activity_at", "expected_responder"])
    if conversation.connection_id:
        identity = ConnectionIdentity.objects.filter(
            connection=conversation.connection, contact=conversation.contact
        ).first()
        transports.send_contact_request(
            conversation.connection,
            chat_id=conversation.external_chat_id,
            user_id=identity.external_user_id if identity else "",
            text=text,
        )
    return message
