from django.db import transaction

from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    ExpectedResponder,
    LifecycleState,
    Message,
    MessageAuthor,
    SystemEvent,
)
from chatballs.conversations.queue import QUEUE_FIELDS, enter_queue, leave_queue
from chatballs.i18n import t
from chatballs.identity.models import EmployeeRole
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
