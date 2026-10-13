"""Напоминание ответить клиенту в принятом диалоге.

Диалог ведёт сотрудник, клиент написал и ждёт. Ожидание начинает первое
сообщение клиента, оставшееся без публичного ответа; следующие сообщения той
же серии срок не сдвигают. Ответ сотрудника ожидание заканчивает, а новое
сообщение клиента после него начинает следующее — со своим сроком и своим
напоминанием.

Факта у сообщения клиента нет, поэтому серию отличает факт, после которого она
пошла: принятие диалога или публичный ответ. Он и есть исходное событие записи,
а момент первого неотвеченного сообщения хранится рядом (`started_at`).

Напоминать можно только тому, кто диалог принял. Назначенный, но ещё не
взявший диалог сотрудник ответа не должен: у его назначения свой срок и свой
возврат в очередь.
"""

from __future__ import annotations

from chatballs.conversations.domain_event_models import (
    ConversationEventActor,
    ConversationEventType,
)
from chatballs.conversations.domain_events import is_accepted
from chatballs.conversations.history_selectors import customer_visible_messages
from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    LifecycleState,
    Message,
    MessageAuthor,
)
from chatballs.conversations.rules import reconcile as reconciling
from chatballs.conversations.rules.models import (
    HandlingRuleKind,
    RuleAction,
    RuleExecution,
    RuleExecutionReason,
)
from chatballs.conversations.rules.recipients import notify_recipients
from chatballs.conversations.rules.reconcile import Wait
from chatballs.tenancy.context import TenantContext

# Факты, с которых принявший диалог сотрудник должен клиенту ответ заново.
_SERIES_FACTS = (ConversationEventType.ACCEPTED, ConversationEventType.PUBLIC_REPLY)
RELEVANT_FACTS = frozenset(
    {
        *_SERIES_FACTS,
        ConversationEventType.ASSIGNED,
        ConversationEventType.TRANSFERRED,
        ConversationEventType.QUEUE_ENTERED,
        ConversationEventType.QUEUE_EXITED,
        ConversationEventType.CLOSED,
    }
)
# Ответом считается реплика человека или агента. Системные записи, включая
# подтверждение получения, клиенту ничего не отвечают.
_REPLY_AUTHORS = (MessageAuthor.OPERATOR, MessageAuthor.AI)


def _is_led_by_human(conversation: Conversation) -> bool:
    return (
        conversation.lifecycle == LifecycleState.OPEN
        and conversation.control_mode == ControlMode.HUMAN
    )


def _first_unanswered(conversation: Conversation) -> Message | None:
    """Первое сообщение клиента после последнего ответа ему.

    Порядок берётся по идентификатору: реплики диалога пишутся под его
    блокировкой, и время записи между транзакциями сравнивать не приходится.
    """
    messages = customer_visible_messages(Message.objects.filter(conversation=conversation))
    last_reply = (
        messages.filter(author_type__in=_REPLY_AUTHORS)
        .order_by("-id")
        .values_list("id", flat=True)
        .first()
    )
    return (
        messages.filter(author_type=MessageAuthor.CONTACT, id__gt=last_reply or 0)
        .order_by("id")
        .first()
    )


def current_wait(conversation: Conversation) -> Wait | None:
    if not _is_led_by_human(conversation) or not is_accepted(conversation):
        return None
    unanswered = _first_unanswered(conversation)
    if unanswered is None:
        return None
    source = (
        conversation.domain_events.filter(event_type__in=_SERIES_FACTS)
        # Mail continuation also records PUBLIC_REPLY for incoming customer mail.
        # Only a human/AI reply ends the previous unanswered series.
        .exclude(event_type=ConversationEventType.PUBLIC_REPLY, actor_kind=ConversationEventActor.CONTACT)
        .order_by("-sequence")
        .first()
    )
    if source is None:
        return None
    # Клиент мог написать ещё в очереди: тогда сотрудник должен ответ с момента,
    # когда диалог стал его, а не с момента сообщения.
    return Wait(source, max(source.occurred_at, unanswered.created_at))


def stale_reason(conversation: Conversation, execution: RuleExecution) -> str:
    """Почему напоминать уже не о чем. Пустая строка — клиент всё ещё ждёт."""
    if conversation.lifecycle != LifecycleState.OPEN:
        return RuleExecutionReason.CONVERSATION_NOT_OPEN
    if not _is_led_by_human(conversation):
        return RuleExecutionReason.NOT_WAITING
    if not is_accepted(conversation):
        return RuleExecutionReason.ASSIGNMENT_REPLACED
    wait = current_wait(conversation)
    if wait is None or wait.source.pk != execution.source_event_id:
        return RuleExecutionReason.REPLIED
    return ""


def reconcile(conversation: Conversation) -> None:
    """Вызывается после факта и после сообщения клиента в диалоге у человека."""
    reconciling.reconcile(
        conversation,
        kind=HandlingRuleKind.REPLY_REMINDER,
        action=RuleAction.REMIND_REPLY,
        wait=current_wait(conversation),
        stale_reason=stale_reason,
    )


def perform(context: TenantContext, conversation: Conversation, execution: RuleExecution) -> dict:
    return notify_recipients(
        context=context,
        conversation=conversation,
        execution=execution,
        title_key="notifications.reply_reminder",
    )
