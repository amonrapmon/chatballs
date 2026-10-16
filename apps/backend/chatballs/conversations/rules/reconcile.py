"""Согласование отложенных действий правила с нынешним состоянием диалога.

У каждого действия своё условие, а шаг один: устаревшие ожидающие записи
снять с причиной, действующему условию поставить срок. Выполняется под
блокировкой диалога — сразу после факта или сообщения, которое могло условие
изменить.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.models import ControlMode, Conversation, LifecycleState
from chatballs.conversations.rules import conditions
from chatballs.conversations.rules.models import RuleExecution, RuleExecutionStatus
from chatballs.conversations.rules.scheduler import schedule, skip
from chatballs.conversations.rules.settings import rule_for


@dataclass(frozen=True, slots=True)
class Wait:
    """Условие действия в силе: от какого факта и с какого момента идёт срок."""

    source: ConversationEvent
    # Пусто — срок идёт от самого факта.
    started_at: datetime | None = None


def waits_in_queue(conversation: Conversation) -> bool:
    """Диалог открыт и ждёт человека в очереди."""
    return (
        conversation.lifecycle == LifecycleState.OPEN
        and conversation.control_mode == ControlMode.PAUSED
        and conversation.waiting_since is not None
    )


def reconcile(
    conversation: Conversation,
    *,
    kind: str,
    action: str,
    wait: Wait | None,
    stale_reason: Callable[[Conversation, RuleExecution], str],
) -> None:
    pending = RuleExecution.objects.filter(
        conversation=conversation, action=action, status=RuleExecutionStatus.PENDING
    )
    if wait is not None:
        pending = pending.exclude(source_event=wait.source)
    for execution in pending:
        skip(execution, stale_reason(conversation, execution))
    if wait is None:
        return
    rule = rule_for(conversation.organization_id, kind)
    if rule.enabled and conditions.matches(rule, conversation):
        schedule(
            rule=rule,
            conversation=conversation,
            source_event=wait.source,
            action=action,
            started_at=wait.started_at,
        )
