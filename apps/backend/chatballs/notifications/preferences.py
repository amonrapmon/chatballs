"""Настройки оклика сотрудника: о чём звать и каким транспортом.

Раньше список типов жил на привязке к мессенджеру. Пока транспорт был один, это
работало; со вторым (браузер) в профиле появились бы два списка галочек про одно
и то же, и человек, отключивший «новое сообщение», продолжал бы получать его с
другой стороны. Поэтому список вынесен из привязки и заведён на транспорт.

Про `enabled` важно не ошибиться: это согласие получать, и у двух транспортов оно
выражено по-разному. У мессенджера согласие — сама привязка бота: она есть, и
звать есть куда; нет — и `enabled` ничего не спасёт. У браузера предъявить нечего,
кроме намерения человека, поэтому его и храним. Отсюда две разные функции ниже:
доставка в мессенджер спрашивает только типы (получателей она уже отобрала по
наличию привязки), а браузер — типы вместе с согласием.
"""

from __future__ import annotations

from chatballs.notifications.models import (
    NotificationPreference,
    NotificationTransport,
    NotificationType,
    default_push_types,
)


def preference_for(
    *, organization_id: int, user_id: int, transport: str
) -> NotificationPreference:
    """Настройка транспорта; при первом обращении заводится с дефолтами."""
    preference, _ = NotificationPreference.objects.get_or_create(
        organization_id=organization_id,
        user_id=user_id,
        transport=transport,
        defaults={"enabled": False, "types": default_push_types()},
    )
    return preference


def preference_types(*, organization_id: int, user_id: int, transport: str) -> list[str]:
    """Типы, выбранные для транспорта. Без строки — дефолтный набор.

    Согласие не проверяется: у мессенджера его подтверждает привязка, и
    отсутствие строки настроек не повод замолчать.
    """
    preference = NotificationPreference.objects.filter(
        organization_id=organization_id, user_id=user_id, transport=transport
    ).first()
    if preference is None:
        return default_push_types()
    return list(preference.types or [])


def enabled_types(*, organization_id: int, user_id: int, transport: str) -> list[str]:
    """Типы транспорта, который человек включил. Не включил — пустой список."""
    preference = NotificationPreference.objects.filter(
        organization_id=organization_id, user_id=user_id, transport=transport
    ).first()
    if preference is None or not preference.enabled:
        return []
    return list(preference.types or [])


def update_preference(
    *,
    organization_id: int,
    user_id: int,
    transport: str,
    enabled: bool | None = None,
    types: list[str] | None = None,
) -> NotificationPreference:
    preference = preference_for(
        organization_id=organization_id, user_id=user_id, transport=transport
    )
    fields = []
    if enabled is not None and preference.enabled != enabled:
        preference.enabled = enabled
        fields.append("enabled")
    if types is not None:
        # Чужие коды в список не пускаем: он приходит из браузера.
        allowed = [code for code in types if code in NotificationType.values]
        if preference.types != allowed:
            preference.types = allowed
            fields.append("types")
    if fields:
        preference.save(update_fields=fields)
    return preference


def messenger_types(*, organization_id: int, user_id: int) -> list[str]:
    return preference_types(
        organization_id=organization_id,
        user_id=user_id,
        transport=NotificationTransport.MESSENGER,
    )
