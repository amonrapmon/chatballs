from django.db import transaction
from django.utils import timezone

from chatballs.conversations import transports
from chatballs.conversations.models import (
    ConnectionIdentity,
    ControlMode,
    Conversation,
    ExpectedResponder,
    LifecycleState,
    Message,
    MessageAuthor,
    MessageKind,
    SystemEvent,
)
from chatballs.conversations.queue import QUEUE_FIELDS, enter_queue, leave_queue
from chatballs.conversations.realtime import notify_conversation_changed
from chatballs.i18n import customer_language, t
from chatballs.identity.models import EmployeeRole
from chatballs.integrations.models import IntegrationProvider
from chatballs.notifications.models import (
    Notification,
    NotificationAudience,
    NotificationType,
)
from chatballs.notifications.services import notify
from chatballs.tenancy.context import TenantContext


class ClaimError(Exception):

    pass





def _require_open(conversation: Conversation) -> None:

    if conversation.lifecycle != LifecycleState.OPEN:

        raise ClaimError(t("conversations.closed"))





def operator_label(operator) -> str:

    return getattr(operator, "full_name", "") or operator.email





@transaction.atomic

def claim_conversation(*, context: TenantContext, conversation_id: int) -> Conversation:

    # Атомарный перехват у AI (ADR-CHATBALLS-0003): только один оператор забирает диалог.

    conversation = Conversation.objects.select_for_update().get(

        id=conversation_id, organization=context.organization

    )

    return claim_locked_conversation(context=context, conversation=conversation)





def claim_locked_conversation(*, context: TenantContext, conversation: Conversation) -> Conversation:

    """Claim an already locked conversation inside the caller's transaction."""

    operator = context.actor_user

    if operator is None or conversation.organization_id != context.organization_id:

        raise ClaimError(t("conversations.unavailable"))

    _require_open(conversation)

    # Владелец (OWNER) может перехватить диалог у любого оператора; прочие сотрудники

    # не могут забрать диалог, уже назначенный другому оператору.

    is_owner = context.membership is not None and context.membership.role == EmployeeRole.OWNER

    if (

        not is_owner

        and conversation.control_mode == ControlMode.HUMAN

        and conversation.assigned_operator_id

        and conversation.assigned_operator_id != operator.id

    ):

        raise ClaimError(t("calls.conversation_taken"))

    conversation.control_mode = ControlMode.HUMAN

    conversation.assigned_operator = operator

    conversation.expected_responder = ExpectedResponder.OPERATOR

    leave_queue(conversation)

    conversation.save(update_fields=["control_mode", "assigned_operator", "expected_responder", "waiting_since"])

    Message.objects.create(

        conversation=conversation,

        author_type=MessageAuthor.SYSTEM,

        system_event=SystemEvent.OPERATOR_TOOK,

        system_params={"operator": operator_label(operator)},

        text=f"Оператор {operator_label(operator)} перехватил диалог",

    )

    return conversation





@transaction.atomic

def release_to_ai(*, context: TenantContext, conversation_id: int) -> Conversation:

    conversation = Conversation.objects.select_for_update().get(

        id=conversation_id, organization=context.organization

    )

    _require_open(conversation)

    agent = getattr(conversation.channel, "ai_agent", None)

    if agent is None or not agent.is_active:

        raise ClaimError(t("channels.no_active_agent"))

    conversation.control_mode = ControlMode.AI

    conversation.assigned_operator = None

    conversation.expected_responder = ExpectedResponder.AI

    leave_queue(conversation)

    conversation.save(update_fields=["control_mode", "assigned_operator", "expected_responder", "waiting_since"])

    Message.objects.create(
        conversation=conversation,
        author_type=MessageAuthor.SYSTEM,
        system_event=SystemEvent.RETURNED_TO_AI,
        text="Диалог возвращён AI",
    )

    return conversation





@transaction.atomic

def return_to_queue(*, context: TenantContext, conversation_id: int) -> Conversation:

    # Оператор возвращает диалог в общую очередь (ADR-CHATBALLS-0003): снят с себя, ждёт оператора.

    conversation = Conversation.objects.select_for_update().get(

        id=conversation_id, organization=context.organization

    )

    _require_open(conversation)

    enter_queue(conversation)

    conversation.assigned_operator = None


    conversation.save(update_fields=[*QUEUE_FIELDS, "assigned_operator"])

    Message.objects.create(
        conversation=conversation,
        author_type=MessageAuthor.SYSTEM,
        system_event=SystemEvent.RETURNED_TO_QUEUE,
        text="Диалог возвращён в очередь",
    )

    return conversation





def post_operator_message(

    *, context: TenantContext, conversation: Conversation, text: str

) -> Message:

    operator = context.actor_user

    if operator is None or conversation.organization_id != context.organization_id:

        raise Conversation.DoesNotExist

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





def request_contact(*, context: TenantContext, conversation: Conversation) -> Message:

    """Запрос контакта у клиента: TG/MAX — сообщение с кнопкой «Поделиться

    контактом», Web — виджет рисует форму телефона по kind=contact_request."""

    operator = context.actor_user

    if operator is None or conversation.organization_id != context.organization_id:

        raise Conversation.DoesNotExist

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





@transaction.atomic

def close_conversation(*, context: TenantContext, conversation_id: int) -> Conversation:

    conversation = Conversation.objects.select_for_update().get(

        id=conversation_id, organization=context.organization

    )

    _require_open(conversation)

    conversation.lifecycle = LifecycleState.CLOSED

    conversation.control_mode = ControlMode.PAUSED

    conversation.assigned_operator = None

    conversation.expected_responder = ExpectedResponder.NOBODY

    leave_queue(conversation)

    conversation.save(

        update_fields=[

            "lifecycle",

            "control_mode",

            "assigned_operator",

            "expected_responder",
            "waiting_since",

        ]

    )

    return conversation





@transaction.atomic

def mark_conversation_as_spam(

    *, context: TenantContext, conversation_id: int

) -> Conversation:

    conversation = Conversation.objects.select_for_update().get(

        id=conversation_id, organization=context.organization

    )

    _require_open(conversation)

    conversation.lifecycle = LifecycleState.SPAM

    conversation.control_mode = ControlMode.PAUSED

    conversation.assigned_operator = None

    conversation.expected_responder = ExpectedResponder.NOBODY

    leave_queue(conversation)

    conversation.save(

        update_fields=[

            "lifecycle",

            "control_mode",

            "assigned_operator",

            "expected_responder",
            "waiting_since",

        ]

    )

    return conversation



@transaction.atomic
def assign_operator(*, context: TenantContext, conversation_id: int, assignee) -> Conversation:
    """Назначить ответственного за диалог (или снять назначение).

    Назначение — не взятие: человек ещё не ответил и мог даже не увидеть
    диалог. Но из общей очереди диалог уходит — отвечать в нём, кроме
    назначенного и руководства, уже никто не может, — поэтому назначенного надо
    позвать лично и поставить срок. Не успел — диалог возвращается в общую
    очередь (chatballs.conversations.escalation).

    Раньше эта операция молча писала внешний ключ: назначенный не узнавал,
    диалог продолжал числиться в общей очереди, а взять его оттуда было уже
    нельзя.
    """
    conversation = Conversation.objects.select_for_update().get(
        id=conversation_id, organization=context.organization
    )
    _require_open(conversation)
    conversation.assigned_operator = assignee
    conversation.assigned_at = timezone.now() if assignee is not None else None
    conversation.save(update_fields=["assigned_operator", "assigned_at"])
    if assignee is None:
        return conversation
    Message.objects.create(
        conversation=conversation,
        author_type=MessageAuthor.SYSTEM,
        system_event=SystemEvent.ASSIGNED_TO,
        system_params={"operator": operator_label(assignee)},
        text=f"Диалог назначен на {operator_label(assignee)}",
    )
    # Себе назначил — сам и знает.
    if context.actor_user is not None and assignee.pk == context.actor_user.pk:
        return conversation
    contact_name = getattr(conversation.contact, "name", "") or t("conversations.guest")
    notify(
        context=context,
        type=NotificationType.DIALOG_ASSIGNED,
        audience=NotificationAudience.USER,
        recipient_user=assignee,
        title=f"Вам назначен диалог · {contact_name}",
        title_key="notifications.assigned_to_you",
        text_params={"contact": contact_name},
        target_id=conversation.id,
        source_type="Conversation",
        source_id=conversation.id,
        dedup_key=f"assign:{conversation.id}:{assignee.pk}",
    )
    return conversation


@transaction.atomic
def delete_conversation(*, context: TenantContext, conversation: Conversation) -> None:
    """Удалить диалог насовсем: переписку, вложения, звонки и оклики о нём.

    Раньше «удалить» означало архив: диалог пропадал из списков, но продолжал
    жить — в него приходили сообщения из канала, он поднимал уведомления и
    возвращался клиенту в виджете как ни в чём не бывало. Решение владельца
    2026-09-14: удалён — значит удалён. Права на это есть только у владельца и
    администратора (проверяет представление).

    Файлы удаляются явно: `FileField` при удалении строки оставляет их на
    диске, а «удалён» не должно означать «лежит в media».
    """
    conversation_id = conversation.id
    organization_id = conversation.organization_id
    for message in conversation.messages.exclude(audio="", attachment=""):
        if message.audio:
            message.audio.delete(save=False)
        if message.attachment:
            message.attachment.delete(save=False)
    # Оклик ведёт в диалог, которого больше нет: и в списке уведомлений, и в
    # мессенджере сотрудника такая строка — тупик.
    Notification.objects.filter(
        organization_id=organization_id,
        source_type="Conversation",
        source_id=str(conversation_id),
    ).delete()
    # Звонки держат диалог внешним ключом PROTECT; история звонка без самого
    # диалога ничего не значит, поэтому уходит вместе с ним.
    from chatballs.calls.models import CallSession

    CallSession.objects.filter(conversation_id=conversation_id).delete()
    conversation.delete()
    # Открытые рабочие места узнают об этом событием: у того, кто держал диалог
    # открытым, он должен закрыться, а не висеть мёртвой карточкой.
    notify_conversation_changed(conversation_id, organization_id=organization_id)
