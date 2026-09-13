from chatballs.events.handlers import register
from chatballs.notifications.delivery import NOTIFICATION_CREATED, deliver_notification
from chatballs.notifications.models import Notification
from chatballs.notifications.realtime import notify_notifications_changed
from chatballs.notifications.recipients import recipient_user_ids
from chatballs.tenancy.context import TenantContext


@register(NOTIFICATION_CREATED)
def handle_notification_created(payload: dict, context: TenantContext | None) -> None:
    if context is None:
        raise ValueError("Notification event has no tenant context")
    notification = Notification.objects.filter(
        pk=payload.get("notificationId"), organization=context.organization
    ).first()
    if notification is None:
        return
    # Получатели считаются один раз на оба пути доставки.
    user_ids = recipient_user_ids(notification)
    # Сначала те, кто сидит в приложении: это мгновенно и ничего не стоит.
    # Мессенджер — следом, он медленнее и ходит наружу.
    notify_notifications_changed(user_ids)
    deliver_notification(notification, user_ids=user_ids)
