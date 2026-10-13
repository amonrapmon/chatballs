"""Журнал исполнений правил: кому он виден и что в нём показывается.

Руководство видит журнал организации целиком. Супервизор — записи обращений
своей области контроля: по группе, в которой обращение находится сейчас.
Остальным журнал не отдаётся.

Наружу уходят коды и идентификаторы: причина пропуска или ошибки — код из
перечня и его подпись на языке читателя. Текста исключений, содержимого
переписки и настроек подключений в журнале нет.
"""

from __future__ import annotations

from collections.abc import Iterable

from django.db.models import QuerySet
from rest_framework.exceptions import PermissionDenied, ValidationError

from chatballs.conversations.rules.models import (
    HandlingRuleKind,
    RuleExecution,
    RuleExecutionStatus,
)
from chatballs.i18n import t
from chatballs.identity.models import OrganizationMembership
from chatballs.identity.policy import ResourceScope, authorize, conversation_visibility
from chatballs.tenancy.context import TenantContext


def _visible(context: TenantContext) -> QuerySet[RuleExecution]:
    executions = RuleExecution.objects.filter(organization_id=context.organization_id)
    if authorize(context.membership, "settings.view", ResourceScope(context.organization_id)):
        return executions
    scope = conversation_visibility(context.membership) or {}
    supervised = scope.get("supervised_group_ids")
    if not supervised:
        raise PermissionDenied(t("rules.journal_forbidden"))
    return executions.filter(conversation__group_id__in=supervised)


def _choice(params, name: str, allowed: Iterable[str]) -> str | None:
    value = params.get(name)
    if value in (None, ""):
        return None
    if value not in allowed:
        raise ValidationError({name: t("rules.journal_filter_invalid")})
    return value


def _conversation_id(params) -> int | None:
    value = params.get("conversationId")
    if value in (None, ""):
        return None
    if not str(value).isascii() or not str(value).isdigit():
        raise ValidationError({"conversationId": t("rules.journal_filter_invalid")})
    return int(value)


def journal_for(context: TenantContext, params) -> QuerySet[RuleExecution]:
    """Записи журнала, доступные читателю, с отбором из запроса."""
    executions = _visible(context)
    kind = _choice(params, "kind", HandlingRuleKind.values)
    status = _choice(params, "status", RuleExecutionStatus.values)
    conversation_id = _conversation_id(params)
    if kind:
        executions = executions.filter(rule__kind=kind)
    if status:
        executions = executions.filter(status=status)
    if conversation_id is not None:
        executions = executions.filter(conversation_id=conversation_id)
    return executions.select_related("rule", "source_event").order_by("-scheduled_for", "-id")


def recipient_names(organization_id: int, executions: Iterable[RuleExecution]) -> dict[int, str]:
    """Имена оповещённых сотрудников этой организации — одним запросом на страницу."""
    user_ids = {user_id for execution in executions for user_id in execution.recipient_user_ids}
    if not user_ids:
        return {}
    profiles = OrganizationMembership.objects.select_related("user").filter(
        organization_id=organization_id, user_id__in=user_ids
    )
    return {profile.user_id: profile.user.full_name or profile.user.email for profile in profiles}


def _stamp(value) -> str | None:
    return value.isoformat() if value else None


def execution_payload(execution: RuleExecution, names: dict[int, str]) -> dict[str, object]:
    source = execution.source_event
    return {
        "id": execution.pk,
        "rule": {"kind": execution.rule.kind, "version": execution.rule_version},
        "action": execution.action,
        "conversationId": execution.conversation_id,
        "sourceEvent": {
            "id": source.pk,
            "type": source.event_type,
            "occurredAt": _stamp(source.occurred_at),
        },
        "startedAt": _stamp(execution.started_at or source.occurred_at),
        "scheduledFor": _stamp(execution.scheduled_for),
        "finishedAt": _stamp(execution.finished_at),
        "status": execution.status,
        "reason": execution.reason,
        "reasonLabel": t(f"rules.reason_{execution.reason}") if execution.reason else "",
        "attempts": execution.attempts,
        "messageId": execution.message_id,
        "notificationId": execution.notification_id,
        # Уволенный или переведённый в другую организацию сотрудник остаётся
        # в записи идентификатором, но имени здесь уже не получает.
        "recipients": [
            {"userId": user_id, "name": names.get(user_id, "")}
            for user_id in execution.recipient_user_ids
        ],
    }
