"""Условия правил первого выпуска: проверка значения и само сравнение.

Условие — ключ и значение из перечня ниже. Что значение допустимо, проверяется
при сохранении настройки; выполняется ли оно для обращения — при постановке
действия и ещё раз перед исполнением, по настройке на тот момент.
"""

from __future__ import annotations

from collections.abc import Callable

from chatballs.channels.models import Channel
from chatballs.conversations.rules.models import HandlingRule

# Правило действует только на обращения перечисленных каналов. Пусто — на все.
CHANNELS = "channelIds"
# Оповещать только тех, кто сейчас в рабочем статусе «готов». Это рабочая
# доступность, выбранная самим сотрудником, а не присутствие за экраном.
AVAILABLE_ONLY = "availableOnly"


def _valid_channels(value: object, organization_id: int) -> bool:
    if not isinstance(value, list):
        return False
    if not all(isinstance(item, int) and not isinstance(item, bool) for item in value):
        return False
    if len(set(value)) != len(value):
        return False
    known = Channel.objects.filter(organization_id=organization_id, pk__in=value).count()
    return known == len(value)


def _valid_flag(value: object, organization_id: int) -> bool:
    return isinstance(value, bool)


VALIDATORS: dict[str, Callable[[object, int], bool]] = {
    CHANNELS: _valid_channels,
    AVAILABLE_ONLY: _valid_flag,
}


def matches(rule: HandlingRule, conversation) -> bool:
    """Обращение подходит под условия отбора правила."""
    channels = rule.conditions.get(CHANNELS)
    return not channels or conversation.channel_id in channels


def available_only(rule: HandlingRule) -> bool:
    return rule.conditions.get(AVAILABLE_ONLY) is True
