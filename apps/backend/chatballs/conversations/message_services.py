from django.utils import timezone

from chatballs.conversations import transports
from chatballs.conversations.access import require_conversation_action
from chatballs.conversations.domain_operations import domain_operation
from chatballs.conversations.models import (
    ConnectionIdentity,
    Conversation,
    ExpectedResponder,
    Message,
    MessageAuthor,
    MessageKind,
)
from chatballs.conversations.service_common import _require_open
from chatballs.i18n import customer_language, t
from chatballs.integrations.models import IntegrationProvider
from chatballs.tenancy.context import TenantContext


@domain_operation("PUBLIC_REPLY")
def post_operator_message(
    *, context: TenantContext, conversation: Conversation, text: str

) -> Message:
    operator = context.actor_user
    if operator is None or conversation.organization_id != context.organization_id:
        raise Conversation.DoesNotExist
    require_conversation_action(context, conversation, "conversations.operate")
    _require_open(conversation)
    message = Message.objects.create(
        conversation=conversation, author_type=MessageAuthor.OPERATOR, author_user=operator, text=text
    )
    conversation.last_activity_at = timezone.now()
    conversation.expected_responder = ExpectedResponder.CUSTOMER
    conversation.save(update_fields=["last_activity_at", "expected_responder"])
    # Отправляем в тот же мессенджер, откуда пришёл клиент.
    if conversation.connection_id:
        identity = ConnectionIdentity.objects.filter(
            connection=conversation.connection, contact=conversation.contact
        ).first()
        transports.send_reply(
            conversation.connection,
            chat_id=conversation.external_chat_id,
            user_id=identity.external_user_id if identity else "",
            text=text,
        )
    return message

@domain_operation("PUBLIC_REPLY")
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
