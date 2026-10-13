"""Отложенное действие правила: постановка, перенос и снятие.

Запись журнала и событие outbox создаются одной транзакцией вызывающего: либо
есть и строка, и событие, которое её разбудит, либо нет ничего. Срок считается
от исходного факта, а не от момента постановки, поэтому повторная постановка
того же действия ничего не сдвигает.

Событие несёт срок, на который оно поставлено. После переноса старое событие
приходит с прежним сроком и отбрасывается исполнителем: живым остаётся одно.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone

from chatballs.conversations.rules.models import (
    HandlingRule,
    RuleExecution,
    RuleExecutionReason,
    RuleExecutionStatus,
)
from chatballs.events.services import DomainEvent, enqueue_event
from chatballs.tenancy.context import TenantActorKind, TenantContext

RULE_EXECUTION_DUE = "conversation.rule_execution_due"


def due_at(rule: HandlingRule, source_event) -> datetime:
    return source_event.occurred_at + timedelta(minutes=rule.delay_minutes)


def _enqueue(execution: RuleExecution) -> None:
    enqueue_event(
        DomainEvent(
            # Свой агрегат: действие правила не должно ждать хода AI в диалоге.
            aggregate_type="RuleExecution",
            aggregate_id=str(execution.pk),
            event_type=RULE_EXECUTION_DUE,
            payload={
                "executionId": execution.pk,
                "scheduledFor": execution.scheduled_for.isoformat(),
            },
            tenant_context=TenantContext.for_resource(
                execution.organization, actor_kind=TenantActorKind.SYSTEM
            ),
        ),
        available_at=execution.scheduled_for,
    )


def realign(execution: RuleExecution, rule: HandlingRule) -> None:
    """Привести действие к действующей настройке правила: версия и срок."""
    scheduled_for = due_at(rule, execution.source_event)
    moved = scheduled_for != execution.scheduled_for or execution.status != RuleExecutionStatus.PENDING
    execution.rule_version = rule.version
    execution.scheduled_for = scheduled_for
    execution.status = RuleExecutionStatus.PENDING
    execution.reason = ""
    execution.finished_at = None
    execution.save(
        update_fields=["rule_version", "scheduled_for", "status", "reason", "finished_at"]
    )
    if moved:
        _enqueue(execution)


def schedule(*, rule: HandlingRule, conversation, source_event, action: str) -> RuleExecution:
    """Поставить действие по исходному факту. Повтор возвращает ту же запись."""
    execution, created = RuleExecution.objects.get_or_create(
        organization_id=conversation.organization_id,
        rule=rule,
        source_event=source_event,
        action=action,
        defaults={
            "conversation": conversation,
            "rule_version": rule.version,
            "scheduled_for": due_at(rule, source_event),
        },
    )
    if created:
        _enqueue(execution)
    elif (
        execution.status == RuleExecutionStatus.SKIPPED
        and execution.reason == RuleExecutionReason.RULE_DISABLED
    ):
        # Правило включили снова, а условие всё ещё в силе: иначе обращение,
        # попавшее под выключение, осталось бы без срока навсегда.
        realign(execution, rule)
    return execution


def skip(execution: RuleExecution, reason: str) -> None:
    execution.status = RuleExecutionStatus.SKIPPED
    execution.reason = reason
    execution.finished_at = timezone.now()
    execution.save(update_fields=["status", "reason", "finished_at"])


def apply_rule_change(rule: HandlingRule) -> None:
    """Довести изменение настройки до ожидающих действий правила."""
    pending = (
        RuleExecution.objects.select_for_update(of=("self",))
        .select_related("source_event")
        .filter(rule=rule, status=RuleExecutionStatus.PENDING)
    )
    for execution in pending:
        if rule.enabled:
            realign(execution, rule)
        else:
            skip(execution, RuleExecutionReason.RULE_DISABLED)
