"""Что можно настроить у каждого правила.

Настройка правила — данные, а не код: условия и получатели задаются ключами
отсюда, и ничего, кроме перечисленного, сервер не примет и не выполнит.
Каталог условий первого выпуска ещё не согласован, поэтому у всех правил он
пуст: условие появляется здесь вместе со своей проверкой, а не раньше.
"""

from __future__ import annotations

from dataclasses import dataclass

from rest_framework.exceptions import ValidationError

from chatballs.conversations.rules.models import (
    MAX_DELAY_MINUTES,
    HandlingRuleKind,
    RuleRecipient,
)
from chatballs.i18n import t


@dataclass(frozen=True, slots=True)
class RuleSpec:
    conditions: frozenset[str] = frozenset()
    recipients: frozenset[str] = frozenset()
    default_recipients: tuple[str, ...] = ()
    # Действие правила реализовано. Без этого включать нечего: включённое
    # правило, которое ничего не делает, хуже выключенного.
    available: bool = False
    enabled_by_default: bool = False


CATALOG: dict[str, RuleSpec] = {
    HandlingRuleKind.RECEIPT_CONFIRMATION: RuleSpec(),
    HandlingRuleKind.WAIT_EXCEEDED_NOTICE: RuleSpec(),
    HandlingRuleKind.REPLY_REMINDER: RuleSpec(),
    # Возврат работал и до правил, поэтому включён сразу и зовёт тех же, кого
    # звал: группу диалога.
    HandlingRuleKind.ASSIGNMENT_RETURN: RuleSpec(
        recipients=frozenset({RuleRecipient.CONVERSATION_GROUP}),
        default_recipients=(RuleRecipient.CONVERSATION_GROUP,),
        available=True,
        enabled_by_default=True,
    ),
}

EDITABLE_FIELDS = ("enabled", "delay_minutes", "conditions", "recipients")


def _valid_delay(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= MAX_DELAY_MINUTES


def validate_settings(kind: str, values: dict) -> None:
    """Проверить настройку правила целиком: и новые поля, и прежние."""
    spec = CATALOG[kind]
    if not isinstance(values["enabled"], bool):
        raise ValidationError({"enabled": t("rules.enabled_invalid")})
    if not _valid_delay(values["delay_minutes"]):
        raise ValidationError({"delay_minutes": t("settings.queue_minutes_range")})
    conditions = values["conditions"]
    if not isinstance(conditions, dict) or not set(conditions) <= spec.conditions:
        raise ValidationError({"conditions": t("rules.conditions_invalid")})
    recipients = values["recipients"]
    if (
        not isinstance(recipients, list)
        or not all(isinstance(item, str) for item in recipients)
        or len(set(recipients)) != len(recipients)
        or not set(recipients) <= spec.recipients
    ):
        raise ValidationError({"recipients": t("rules.recipients_invalid")})
    if not values["enabled"]:
        return
    if not spec.available:
        raise ValidationError({"enabled": t("rules.unavailable")})
    if values["delay_minutes"] is None:
        raise ValidationError({"delay_minutes": t("settings.queue_minutes_range")})
    if spec.recipients and not recipients:
        raise ValidationError({"recipients": t("rules.recipients_required")})
