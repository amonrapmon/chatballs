"""Возврат назначенного, но не принятого обращения в общую очередь.

Назначение уводит диалог из общей очереди: отвечать в нём, кроме назначенного
и руководства, уже некому. Поэтому у назначения есть срок — не взял, значит
диалог возвращается всем. Срок идёт от факта конкретного назначения: повторное
сообщение клиента его не сдвигает, а новое назначение получает свой.

Раньше возврат делал обход очереди, сверяя время назначения. Теперь он
ставится в момент назначения и выполняется под блокировкой диалога: принятое
или заменённое назначение уже не снять, даже если воркер опоздал или повторил
работу.
"""

from __future__ import annotations

import logging

from chatballs.conversations.domain_event_models import ConversationEvent, ConversationEventType
from chatballs.conversations.domain_events import operation_key, record_fact
from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    LifecycleState,
    Message,
    MessageAuthor,
    SystemEvent,
)
from chatballs.conversations.rules.models import (
    HandlingRuleKind,
    RuleAction,
    RuleExecution,
    RuleExecutionReason,
    RuleExecutionStatus,
    RuleRecipient,
)
from chatballs.conversations.rules.scheduler import schedule, skip
from chatballs.conversations.rules.settings import rule_for
from chatballs.conversations.service_common import operator_label
from chatballs.i18n import t
from chatballs.notifications.models import (
    NotificationAudience,
    NotificationLevel,
    NotificationType,
)
from chatballs.notifications.services import notify
from chatballs.tenancy.context import TenantContext

logger = logging.getLogger(__name__)

_ASSIGNMENT_FACTS = (ConversationEventType.ASSIGNED, ConversationEventType.TRANSFERRED)
# Факты, после которых назначение могло появиться, смениться или перестать ждать.
RELEVANT_FACTS = frozenset(
    {
        *_ASSIGNMENT_FACTS,
        ConversationEventType.ACCEPTED,
        ConversationEventType.QUEUE_ENTERED,
        ConversationEventType.QUEUE_EXITED,
        ConversationEventType.CLOSED,
    }
)


def _is_waiting(conversation: Conversation) -> bool:
    return (
        conversation.lifecycle == LifecycleState.OPEN
        and conversation.control_mode == ControlMode.PAUSED
        and conversation.waiting_since is not None
    )


def current_assignment(conversation: Conversation) -> ConversationEvent | None:
    """Факт, которым назначен нынешний ответственный."""
    if conversation.assigned_operator_id is None:
        return None
    fact = (
        conversation.domain_events.filter(event_type__in=_ASSIGNMENT_FACTS)
        .order_by("-sequence")
        .first()
    )
    if fact is None or fact.responsible_id != conversation.assigned_operator_id:
        return None
    return fact


def stale_reason(conversation: Conversation, execution: RuleExecution) -> str:
    """Почему возвращать уже нечего. Пустая строка — назначение всё ещё ждёт."""
    if conversation.lifecycle != LifecycleState.OPEN:
        return RuleExecutionReason.CONVERSATION_NOT_OPEN
    if conversation.assigned_operator_id is None:
        return RuleExecutionReason.ASSIGNMENT_REMOVED
    current = current_assignment(conversation)
    if current is None or current.pk != execution.source_event_id:
        return RuleExecutionReason.ASSIGNMENT_REPLACED
    # В работу диалог переводит только взятие, а взять его у назначенного
    # может лишь он сам — иначе назначение уже было бы заменено.
    if conversation.control_mode == ControlMode.HUMAN:
        return RuleExecutionReason.ASSIGNMENT_ACCEPTED
    if not _is_waiting(conversation):
        return RuleExecutionReason.NOT_WAITING
    return ""


def reconcile(conversation: Conversation) -> None:
    """Привести отложенные возвраты в согласие с состоянием диалога.

    Вызывается под блокировкой диалога после факта, который мог изменить
    назначение, и из обхода очереди — тот подбирает назначения, сделанные до
    появления правил или пока правило было выключено.
    """
    source = current_assignment(conversation) if _is_waiting(conversation) else None
    pending = RuleExecution.objects.filter(
        conversation=conversation,
        action=RuleAction.RETURN_TO_QUEUE,
        status=RuleExecutionStatus.PENDING,
    )
    if source is not None:
        pending = pending.exclude(source_event=source)
    for execution in pending:
        skip(execution, stale_reason(conversation, execution))
    if source is None:
        return
    rule = rule_for(conversation.organization_id, HandlingRuleKind.ASSIGNMENT_RETURN)
    if rule.enabled:
        schedule(
            rule=rule,
            conversation=conversation,
            source_event=source,
            action=RuleAction.RETURN_TO_QUEUE,
        )


def perform(context: TenantContext, conversation: Conversation, execution: RuleExecution) -> dict:
    """Снять назначение. Диалог остаётся в очереди и ждёт с прежнего момента."""
    label = operator_label(conversation.assigned_operator)
    conversation.assigned_operator = None
    conversation.assigned_at = None
    conversation.save(update_fields=["assigned_operator", "assigned_at"])
    record_fact(
        conversation,
        ConversationEventType.TRANSFERRED,
        operation_id=operation_key("rule-execution", execution.pk),
    )
    message = Message.objects.create(
        conversation=conversation,
        author_type=MessageAuthor.SYSTEM,
        system_event=SystemEvent.ASSIGNMENT_EXPIRED,
        system_params={"operator": label},
        text="",
    )
    logger.info("Assignment on conversation %s expired", conversation.id)
    notification = None
    if RuleRecipient.CONVERSATION_GROUP in execution.rule.recipients:
        contact = getattr(conversation.contact, "name", "") or t("conversations.guest")
        notification = notify(
            context=context,
            type=NotificationType.OPERATOR_REQUESTED,
            audience=NotificationAudience.OPERATORS,
            audience_group=conversation.group,
            level=NotificationLevel.WARNING,
            title="",
            title_key="notifications.assignment_expired",
            text_params={"contact": contact, "operator": label},
            target_id=conversation.id,
            source_type="Conversation",
            source_id=conversation.id,
            # Ключ действия, а не диалога: у каждого назначения свой возврат и
            # свой оклик, а повтор того же действия второго не создаёт.
            dedup_key=f"rule-execution:{execution.pk}",
        )
    return {"message": message, "notification": notification}
