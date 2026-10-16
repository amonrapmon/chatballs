"""Уведомление о превышении ожидания в очереди.

Срок идёт от факта входа в очередь: повторное сообщение клиента его не
сдвигает, а новый вход в очередь получает свой. Диалог вышел из очереди —
взяли, вернули AI, закрыли — и предупреждать уже не о чем.

Пороги раздела «Когда звать на помощь» и обход ждущих диалогов это правило не
заменяет и не трогает: они работают как прежде.
"""

from __future__ import annotations

from chatballs.conversations.domain_event_models import ConversationEvent, ConversationEventType
from chatballs.conversations.models import Conversation, LifecycleState
from chatballs.conversations.rules import reconcile as reconciling
from chatballs.conversations.rules.models import (
    HandlingRuleKind,
    RuleAction,
    RuleExecution,
    RuleExecutionReason,
)
from chatballs.conversations.rules.recipients import notify_recipients
from chatballs.conversations.rules.reconcile import Wait, waits_in_queue
from chatballs.tenancy.context import TenantContext

RELEVANT_FACTS = frozenset(
    {
        ConversationEventType.QUEUE_ENTERED,
        ConversationEventType.QUEUE_EXITED,
        ConversationEventType.ACCEPTED,
        ConversationEventType.CLOSED,
    }
)


def current_entry(conversation: Conversation) -> ConversationEvent | None:
    """Факт, которым диалог встал в очередь, где ждёт сейчас."""
    if not waits_in_queue(conversation):
        return None
    return (
        conversation.domain_events.filter(event_type=ConversationEventType.QUEUE_ENTERED)
        .order_by("-sequence")
        .first()
    )


def stale_reason(conversation: Conversation, execution: RuleExecution) -> str:
    """Почему предупреждать уже не о чем. Пустая строка — ожидание то же."""
    if conversation.lifecycle != LifecycleState.OPEN:
        return RuleExecutionReason.CONVERSATION_NOT_OPEN
    entry = current_entry(conversation)
    if entry is None or entry.pk != execution.source_event_id:
        return RuleExecutionReason.NOT_WAITING
    return ""


def reconcile(conversation: Conversation) -> None:
    entry = current_entry(conversation)
    reconciling.reconcile(
        conversation,
        kind=HandlingRuleKind.WAIT_EXCEEDED_NOTICE,
        action=RuleAction.NOTIFY_WAIT_EXCEEDED,
        wait=Wait(entry) if entry is not None else None,
        stale_reason=stale_reason,
    )


def perform(context: TenantContext, conversation: Conversation, execution: RuleExecution) -> dict:
    return notify_recipients(
        context=context,
        conversation=conversation,
        execution=execution,
        title_key="notifications.wait_exceeded",
    )
