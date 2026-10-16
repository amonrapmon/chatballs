"""Подтверждение получения обращения со сроком ответа.

Клиент получает его один раз на обращение — когда оно впервые встаёт в очередь
к человеку: новое обращение на канале без работающего агента либо передача от
агента. Обращение, на которое сразу отвечает агент, обещания «ответим через…»
не получает.

Текст и срок задаёт организация. Своего текста у сервера нет: без него правило
не включается, а ожидающая запись завершается пропуском. В сообщение идёт
только этот текст и срок словами на языке организации — ни причин, ни кодов,
ни внутренних сведений.

Подтверждение — системная запись ленты, а не ответ: оно не считается публичным
ответом, не снимает ожидание и не останавливает напоминания.
"""

from __future__ import annotations

from chatballs.conversations.domain_event_models import ConversationEvent, ConversationEventType
from chatballs.conversations.models import Conversation, LifecycleState, Message, MessageAuthor
from chatballs.conversations.rules import reconcile as reconciling
from chatballs.conversations.rules.deadline_text import render
from chatballs.conversations.rules.models import (
    HandlingRuleKind,
    RuleAction,
    RuleExecution,
    RuleExecutionReason,
)
from chatballs.conversations.rules.reconcile import Wait, waits_in_queue
from chatballs.events.services import DomainEvent, enqueue_event
from chatballs.i18n import customer_language
from chatballs.tenancy.context import TenantContext

RULE_MESSAGE_DELIVERY = "conversation.rule_message_delivery"

RELEVANT_FACTS = frozenset(
    {
        ConversationEventType.QUEUE_ENTERED,
        ConversationEventType.QUEUE_EXITED,
        ConversationEventType.ACCEPTED,
        ConversationEventType.CLOSED,
    }
)


def first_entry(conversation: Conversation) -> ConversationEvent | None:
    """Факт первого входа в очередь — если диалог всё ещё ждёт именно с него."""
    if not waits_in_queue(conversation):
        return None
    entries = list(
        conversation.domain_events.filter(event_type=ConversationEventType.QUEUE_ENTERED)
        .order_by("sequence")[:2]
    )
    return entries[0] if len(entries) == 1 else None


def stale_reason(conversation: Conversation, execution: RuleExecution) -> str:
    """Почему подтверждать уже нечего или нечем. Пустая строка — отправлять."""
    if conversation.lifecycle != LifecycleState.OPEN:
        return RuleExecutionReason.CONVERSATION_NOT_OPEN
    entry = first_entry(conversation)
    if entry is None or entry.pk != execution.source_event_id:
        return RuleExecutionReason.NOT_WAITING
    if not execution.rule.text.strip():
        return RuleExecutionReason.SETTINGS_INCOMPLETE
    if conversation.connection_id is None:
        return RuleExecutionReason.CONNECTION_MISSING
    return ""


def reconcile(conversation: Conversation) -> None:
    entry = first_entry(conversation)
    reconciling.reconcile(
        conversation,
        kind=HandlingRuleKind.RECEIPT_CONFIRMATION,
        action=RuleAction.SEND_CONFIRMATION,
        wait=Wait(entry) if entry is not None else None,
        stale_reason=stale_reason,
    )


def perform(context: TenantContext, conversation: Conversation, execution: RuleExecution) -> dict:
    """Записать подтверждение в ленту и поставить его отправку клиенту."""
    rule = execution.rule
    message = Message.objects.create(
        conversation=conversation,
        author_type=MessageAuthor.SYSTEM,
        text=render(
            rule.text.strip(), rule.delay_minutes, customer_language(conversation.organization)
        ),
        # По этому ключу запись ленты связана с действием правила.
        external_id=f"rule-execution:{execution.pk}",
    )
    # Мессенджер — сеть: в транзакцию действия она не входит. Запись ленты и
    # событие отправки появляются вместе, а неопределённый исход доставки
    # остаётся за событием.
    enqueue_event(
        DomainEvent(
            aggregate_type="RuleExecution",
            aggregate_id=str(execution.pk),
            event_type=RULE_MESSAGE_DELIVERY,
            payload={"messageId": message.pk},
            tenant_context=context,
        )
    )
    return {"message": message}
