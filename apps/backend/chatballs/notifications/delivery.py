"""Доставка уведомлений в мессенджеры через сервисных ботов.

Событие notifications.notification_created кладётся в outbox из notify() и
обрабатывается worker'ом: аудитория разворачивается в получателей
(chatballs.notifications.recipients), их привязки получают сообщение через
транспорт бота.

Отправка best-effort: сбой одной привязки логируется и не валит событие.
"""

from __future__ import annotations

import logging

from chatballs.conversations import transports
from chatballs.identity.instance_settings import public_base_url
from chatballs.notifications.models import (
    MessengerBinding,
    Notification,
    NotificationLevel,
)
from chatballs.notifications.preferences import messenger_types
from chatballs.notifications.recipients import recipient_user_ids

logger = logging.getLogger(__name__)

NOTIFICATION_CREATED = "notifications.notification_created"

_LEVEL_MARK = {
    NotificationLevel.INFO: "🔔",
    NotificationLevel.SUCCESS: "✅",
    NotificationLevel.WARNING: "⚠️",
    NotificationLevel.CRITICAL: "🔴",
}


def _message_text(notification: Notification) -> str:
    mark = _LEVEL_MARK.get(notification.level, "🔔")
    lines = [f"{mark} {notification.title}"]
    if notification.body:
        lines.append(notification.body)
    base_url = public_base_url()
    if base_url:
        lines.append(base_url)
    return "\n".join(lines)


def deliver_notification(notification: Notification, *, user_ids: list[int] | None = None) -> int:
    """Рассылает уведомление в привязанные мессенджеры.

    Получателей можно передать готовыми: тот же список нужен и оповещению
    открытого приложения, а считать его дважды на каждое уведомление незачем.
    """
    if user_ids is None:
        user_ids = recipient_user_ids(notification)
    if not user_ids:
        return 0
    bindings = (
        MessengerBinding.objects.select_related("integration")
        .filter(user_id__in=user_ids, integration__organization_id=notification.organization_id)
    )
    text = _message_text(notification)
    sent = 0
    for binding in bindings:
        allowed = messenger_types(
            organization_id=notification.organization_id, user_id=binding.user_id
        )
        if notification.type not in allowed:
            continue
        try:
            if transports.send_reply(binding.integration, chat_id=binding.external_chat_id, user_id="", text=text):
                sent += 1
        except Exception:  # pragma: no cover
            logger.exception("Messenger delivery failed for binding %s", binding.id)
    return sent
