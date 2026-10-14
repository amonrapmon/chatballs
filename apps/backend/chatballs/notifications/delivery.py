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
from chatballs.i18n import customer_language, resolve_language, t
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


def _message_text(notification: Notification, *, language=None) -> str:
    mark = _LEVEL_MARK.get(notification.level, "🔔")
    params = notification.text_params or {}
    title = t(notification.title_key, language=language, **params) if notification.title_key else notification.title
    body = t(notification.body_key, language=language, **params) if notification.body_key else notification.body
    lines = [f"{mark} {title}"]
    if body:
        lines.append(body)
    base_url = public_base_url()
    if base_url:
        lines.append(base_url)
    return "\n".join(lines)


def deliver_notification(notification: Notification, *, user_ids: list[int] | None = None) -> int:
    """Рассылает уведомление в привязанные мессенджеры.

    Переданный список получателей — только кандидаты. Текущий доступ
    проверяется при доставке, в том числе перед отправкой каждой привязке.
    """
    current_ids = set(recipient_user_ids(notification))
    user_ids = current_ids if user_ids is None else current_ids.intersection(user_ids)
    if not user_ids:
        return 0
    bindings = (
        MessengerBinding.objects.select_related("integration", "user")
        .filter(user_id__in=user_ids, integration__organization_id=notification.organization_id)
    )
    sent = 0
    for binding in bindings:
        if binding.user_id not in recipient_user_ids(notification):
            continue
        allowed = messenger_types(
            organization_id=notification.organization_id, user_id=binding.user_id
        )
        if notification.type not in allowed:
            continue
        language = resolve_language(
            user_language=binding.user.ui_language,
            organization_language=customer_language(notification.organization),
        )
        text = _message_text(notification, language=language)
        try:
            if transports.send_reply(binding.integration, chat_id=binding.external_chat_id, user_id="", text=text):
                sent += 1
        except Exception:  # pragma: no cover
            logger.exception("Messenger delivery failed for binding %s", binding.id)
    return sent
