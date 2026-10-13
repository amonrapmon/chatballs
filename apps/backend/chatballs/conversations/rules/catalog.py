"""Что можно настроить у каждого правила.

Настройка правила — данные, а не код: условия и получатели задаются ключами
отсюда, и ничего, кроме перечисленного, сервер не примет и не выполнит.
Условие появляется здесь вместе со своей проверкой (rules.conditions), а не
раньше.
"""

from __future__ import annotations

from dataclasses import dataclass

from rest_framework.exceptions import ValidationError

from chatballs.conversations.rules.conditions import AVAILABLE_ONLY, CHANNELS, VALIDATORS
from chatballs.conversations.rules.models import (
    MAX_DELAY_MINUTES,
    MAX_TEXT_LENGTH,
    HandlingRuleKind,
    RuleRecipient,
)
from chatballs.i18n import t


@dataclass(frozen=True, slots=True)
class RuleSpec:
    conditions: frozenset[str] = frozenset()
    recipients: frozenset[str] = frozenset()
    default_recipients: tuple[str, ...] = ()
    # Правило пишет клиенту: текст задаёт организация, своего у сервера нет.
    requires_text: bool = False
    enabled_by_default: bool = False


_NOTICE_CONDITIONS = frozenset({CHANNELS, AVAILABLE_ONLY})

CATALOG: dict[str, RuleSpec] = {
    HandlingRuleKind.RECEIPT_CONFIRMATION: RuleSpec(
        conditions=frozenset({CHANNELS}),
        requires_text=True,
    ),
    HandlingRuleKind.WAIT_EXCEEDED_NOTICE: RuleSpec(
        conditions=_NOTICE_CONDITIONS,
        recipients=frozenset(
            {
                RuleRecipient.CONVERSATION_GROUP,
                RuleRecipient.GROUP_SUPERVISORS,
                RuleRecipient.MANAGEMENT,
            }
        ),
    ),
    HandlingRuleKind.REPLY_REMINDER: RuleSpec(
        conditions=_NOTICE_CONDITIONS,
        recipients=frozenset(
            {
                RuleRecipient.ASSIGNEE,
                RuleRecipient.GROUP_SUPERVISORS,
                RuleRecipient.MANAGEMENT,
            }
        ),
    ),
    # Возврат работал и до правил, поэтому включён сразу и зовёт тех же, кого
    # звал: группу диалога.
    HandlingRuleKind.ASSIGNMENT_RETURN: RuleSpec(
        recipients=frozenset({RuleRecipient.CONVERSATION_GROUP}),
        default_recipients=(RuleRecipient.CONVERSATION_GROUP,),
        enabled_by_default=True,
    ),
}

# Поле настройки и его имя в API: ошибка проверки называет поле так, как его
# прислал клиент.
EDITABLE_FIELDS = {
    "enabled": "enabled",
    "delay_minutes": "delayMinutes",
    "conditions": "conditions",
    "recipients": "recipients",
    "text": "text",
}


def _invalid(field: str, key: str, **params: object) -> ValidationError:
    return ValidationError({EDITABLE_FIELDS[field]: t(key, **params)})


def _valid_delay(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= MAX_DELAY_MINUTES


def _check_conditions(spec: RuleSpec, conditions: object, organization_id: int) -> None:
    if not isinstance(conditions, dict) or not set(conditions) <= spec.conditions:
        raise _invalid("conditions", "rules.conditions_invalid")
    for key, value in conditions.items():
        if not VALIDATORS[key](value, organization_id):
            raise _invalid("conditions", "rules.condition_value_invalid")


def _check_recipients(spec: RuleSpec, recipients: object) -> None:
    if (
        not isinstance(recipients, list)
        or not all(isinstance(item, str) for item in recipients)
        or len(set(recipients)) != len(recipients)
        or not set(recipients) <= spec.recipients
    ):
        raise _invalid("recipients", "rules.recipients_invalid")


def _check_text(spec: RuleSpec, text: object) -> None:
    if not isinstance(text, str) or len(text) > MAX_TEXT_LENGTH:
        raise _invalid("text", "rules.text_invalid", limit=MAX_TEXT_LENGTH)
    if text and not spec.requires_text:
        raise _invalid("text", "rules.text_unsupported")


def validate_settings(kind: str, values: dict, *, organization_id: int) -> None:
    """Проверить настройку правила целиком: и новые поля, и прежние."""
    spec = CATALOG[kind]
    if not isinstance(values["enabled"], bool):
        raise _invalid("enabled", "rules.enabled_invalid")
    if not _valid_delay(values["delay_minutes"]):
        raise _invalid("delay_minutes", "settings.queue_minutes_range")
    _check_conditions(spec, values["conditions"], organization_id)
    _check_recipients(spec, values["recipients"])
    _check_text(spec, values["text"])
    if not values["enabled"]:
        return
    # Включённое правило обязано знать всё, что ему нужно для действия: срок,
    # кого звать и что писать. Додумывать за организацию сервер не станет.
    if values["delay_minutes"] is None:
        raise _invalid("delay_minutes", "settings.queue_minutes_range")
    if spec.recipients and not values["recipients"]:
        raise _invalid("recipients", "rules.recipients_required")
    if spec.requires_text and not values["text"].strip():
        raise _invalid("text", "rules.text_required")
