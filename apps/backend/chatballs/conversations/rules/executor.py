"""Исполнитель отложенных действий правил.

Событие outbox — только будильник: что делать, решается заново, под
блокировкой диалога и по его нынешнему состоянию. Отсюда три исхода записи
журнала: выполнено, пропущено с причиной, ошибка.

Повтор безопасен на каждом шаге. Событие, пришедшее второй раз, находит запись
уже завершённой. Упавший посреди работы процесс откатывает транзакцию целиком:
снятое назначение, факт, сообщение, оклик и отметка журнала либо есть все, либо
нет ни одного. Наружу действие в этой транзакции не ходит — оклик уезжает своим
событием outbox, и неопределённый исход доставки остаётся за ним.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from chatballs.conversations.models import Conversation
from chatballs.conversations.rules import (
    assignment_return,
    conditions,
    receipt_confirmation,
    reply_reminder,
    wait_notice,
)
from chatballs.conversations.rules.models import (
    HandlingRule,
    RuleAction,
    RuleExecution,
    RuleExecutionReason,
    RuleExecutionStatus,
)
from chatballs.conversations.rules.scheduler import SkipAction, realign, skip
from chatballs.events.services import MAX_OUTBOX_ATTEMPTS
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ActionHandler:
    # Причина, по которой условие действия больше не выполняется, или "".
    stale_reason: Callable[[Conversation, RuleExecution], str]
    # Само действие. Возвращает ссылки на результат для журнала либо бросает
    # SkipAction, если выполнять оказалось нечего.
    perform: Callable[[TenantContext, Conversation, RuleExecution], dict]


ACTIONS: dict[str, ActionHandler] = {
    RuleAction.RETURN_TO_QUEUE: ActionHandler(
        stale_reason=assignment_return.stale_reason,
        perform=assignment_return.perform,
    ),
    RuleAction.SEND_CONFIRMATION: ActionHandler(
        stale_reason=receipt_confirmation.stale_reason,
        perform=receipt_confirmation.perform,
    ),
    RuleAction.NOTIFY_WAIT_EXCEEDED: ActionHandler(
        stale_reason=wait_notice.stale_reason,
        perform=wait_notice.perform,
    ),
    RuleAction.REMIND_REPLY: ActionHandler(
        stale_reason=reply_reminder.stale_reason,
        perform=reply_reminder.perform,
    ),
}


def _locked_pending(payload: dict, context: TenantContext):
    """Диалог и запись журнала под блокировкой — или None, если работы нет."""
    conversation_id = (
        RuleExecution.objects.filter(
            pk=payload.get("executionId"),
            organization_id=context.organization_id,
            status=RuleExecutionStatus.PENDING,
        )
        .values_list("conversation_id", flat=True)
        .first()
    )
    if conversation_id is None:
        return None
    # Порядок блокировок тот же, что у операций диалога: сначала диалог.
    # Без join: строка, дождавшаяся блокировки, перечитывается, а
    # присоединённые к ней ответственный и группа — нет.
    conversation = Conversation.objects.select_for_update().get(
        pk=conversation_id, organization_id=context.organization_id
    )
    execution = (
        RuleExecution.objects.select_for_update(of=("self",))
        .select_related("source_event")
        .filter(pk=payload["executionId"], status=RuleExecutionStatus.PENDING)
        .first()
    )
    if execution is None:
        return None
    return conversation, execution


def _run(payload: dict, context: TenantContext) -> None:
    locked = _locked_pending(payload, context)
    if locked is None:
        return
    conversation, execution = locked
    rule = HandlingRule.objects.get(pk=execution.rule_id)
    execution.rule, execution.conversation = rule, conversation
    if not rule.enabled:
        skip(execution, RuleExecutionReason.RULE_DISABLED)
        return
    if rule.version != execution.rule_version:
        realign(execution, rule)
    if datetime.fromisoformat(payload["scheduledFor"]) != execution.scheduled_for:
        # Срок перенесли: это событие устарело, запись разбудит другое.
        return
    if not conditions.matches(rule, conversation):
        # Условия отбора поменяли, пока действие ждало срока.
        skip(execution, RuleExecutionReason.CONDITION_NOT_MET)
        return
    handler = ACTIONS[execution.action]
    reason = handler.stale_reason(conversation, execution)
    if reason:
        skip(execution, reason)
        return
    # Отметка раньше действия: факт, который оно запишет, не должен принять
    # эту же запись за ожидающую. Транзакция одна, порядок снаружи не виден.
    execution.status = RuleExecutionStatus.EXECUTED
    execution.finished_at = timezone.now()
    execution.save(update_fields=["status", "finished_at"])
    try:
        outcome = handler.perform(context, conversation, execution)
    except SkipAction as skipped:
        skip(execution, skipped.reason)
        return
    for field, value in outcome.items():
        setattr(execution, field, value)
    execution.save(update_fields=list(outcome))


def _record_failure(payload: dict, context: TenantContext) -> None:
    execution = (
        RuleExecution.objects.select_for_update(of=("self",))
        .filter(
            pk=payload.get("executionId"),
            organization_id=context.organization_id,
            status=RuleExecutionStatus.PENDING,
        )
        .first()
    )
    if execution is None:
        return
    execution.attempts += 1
    fields = ["attempts"]
    if execution.attempts >= MAX_OUTBOX_ATTEMPTS:
        # Outbox больше не повторит: запись не должна остаться ожидающей.
        execution.status = RuleExecutionStatus.FAILED
        execution.reason = RuleExecutionReason.EXECUTION_ERROR
        execution.finished_at = timezone.now()
        fields += ["status", "reason", "finished_at"]
    execution.save(update_fields=fields)


def run_due_execution(payload: dict, context: TenantContext) -> None:
    try:
        with tenant_atomic(context):
            _run(payload, context)
    except Exception:
        # В журнал идёт только код: текст исключения остаётся в логе outbox.
        with tenant_atomic(context):
            _record_failure(payload, context)
        raise
