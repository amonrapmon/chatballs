"""Настройки правил: чтение с дефолтами и изменение с версией.

Строка правила заводится при первом обращении, как и пороги очереди. Менять её
можно только здесь: версия, автор и ожидающие действия обновляются вместе с
настройкой, одной транзакцией.
"""

from __future__ import annotations

from collections.abc import Mapping

from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from chatballs.conversations.queue_models import QueueEscalationPolicy
from chatballs.conversations.rules.catalog import CATALOG, EDITABLE_FIELDS, validate_settings
from chatballs.conversations.rules.models import HandlingRule, HandlingRuleKind
from chatballs.conversations.rules.scheduler import apply_rule_change
from chatballs.i18n import t
from chatballs.identity.policy import ResourceScope, authorize
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic

# Срок возврата назначения — тот же, что в разделе «Когда звать на помощь»:
# одно число, а не два, которые могут разойтись.
_QUEUE_POLICY_DELAY = "assignment_timeout_minutes"


def _default_delay(organization_id: int, kind: str) -> int | None:
    if kind != HandlingRuleKind.ASSIGNMENT_RETURN:
        return None
    saved = (
        QueueEscalationPolicy.objects.filter(organization_id=organization_id)
        .values_list(_QUEUE_POLICY_DELAY, flat=True)
        .first()
    )
    return saved or QueueEscalationPolicy.DEFAULTS[_QUEUE_POLICY_DELAY]


def rule_for(organization_id: int, kind: str) -> HandlingRule:
    rule = HandlingRule.objects.filter(organization_id=organization_id, kind=kind).first()
    if rule is not None:
        return rule
    spec = CATALOG[kind]
    return HandlingRule.objects.get_or_create(
        organization_id=organization_id,
        kind=kind,
        defaults={
            "enabled": spec.enabled_by_default,
            "delay_minutes": _default_delay(organization_id, kind),
            "recipients": list(spec.default_recipients),
        },
    )[0]


def update_rule(*, context: TenantContext, kind: str, changes: Mapping[str, object]) -> HandlingRule:
    """Изменить настройку правила. Без изменений версия не растёт."""
    if not authorize(context.membership, "settings.manage", ResourceScope(context.organization_id)):
        raise PermissionDenied(t("rules.forbidden"))
    with tenant_atomic(context):
        rule = HandlingRule.objects.select_for_update().get(
            pk=rule_for(context.organization_id, kind).pk
        )
        values = {field: changes.get(field, getattr(rule, field)) for field in EDITABLE_FIELDS}
        validate_settings(kind, values)
        changed = [field for field in EDITABLE_FIELDS if getattr(rule, field) != values[field]]
        if not changed:
            return rule
        for field in changed:
            setattr(rule, field, values[field])
        rule.version += 1
        rule.updated_at = timezone.now()
        rule.updated_by = context.actor_user
        rule.save(update_fields=[*changed, "version", "updated_at", "updated_by"])
        if (
            kind == HandlingRuleKind.ASSIGNMENT_RETURN
            and "delay_minutes" in changed
            and rule.delay_minutes is not None
        ):
            QueueEscalationPolicy.objects.update_or_create(
                organization_id=context.organization_id,
                defaults={_QUEUE_POLICY_DELAY: rule.delay_minutes},
            )
        apply_rule_change(rule)
        return rule
