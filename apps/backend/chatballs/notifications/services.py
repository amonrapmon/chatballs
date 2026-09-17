from datetime import timedelta

from django.utils import timezone

from chatballs.events.services import DomainEvent, enqueue_event
from chatballs.identity.models import EmployeeRole, OrganizationMembership
from chatballs.notifications.delivery import NOTIFICATION_CREATED
from chatballs.notifications.models import (
    Notification,
    NotificationAudience,
    NotificationLevel,
    NotificationRead,
    NotificationType,
)
from chatballs.notifications.realtime import notify_notifications_changed
from chatballs.notifications.selectors import unread_for

# Реестр типов: дефолтный уровень и маршрут диплинка. Новый тип события —
# одна запись здесь + вызов notify(...) из доменного сервиса.
# «label» — ключ каталога, а не текст: список типов уходит в профиль, где
# каждый сотрудник читает его на своём языке. Ярлык TextChoices остаётся
# английским/русским значением модели и до человека не доходит.
TYPE_META: dict[str, dict] = {
    NotificationType.NEW_DIALOG: {
        "level": NotificationLevel.INFO,
        "route": "chat",
        "label": "notifications.type_new_dialog",
    },
    NotificationType.OPERATOR_REQUESTED: {
        "level": NotificationLevel.WARNING,
        "route": "chat",
        "label": "notifications.type_operator_requested",
    },
    NotificationType.DIALOG_NEW_MESSAGE: {
        "level": NotificationLevel.INFO,
        "route": "chat",
        "label": "notifications.type_dialog_new_message",
    },
    NotificationType.DIALOG_ASSIGNED: {
        "level": NotificationLevel.INFO,
        "route": "chat",
        "label": "notifications.type_dialog_assigned",
    },
    NotificationType.DIALOG_WAITING_LONG: {
        "level": NotificationLevel.WARNING,
        "route": "chat",
        "label": "notifications.type_dialog_waiting_long",
    },
    NotificationType.AI_STOPPED: {
        "level": NotificationLevel.CRITICAL,
        "route": "agents",
        "label": "notifications.type_ai_stopped",
    },
}


def notify(
    *,
    context,
    type: str,
    audience: str,
    audience_group=None,
    title: str,
    body: str = "",
    title_key: str = "",
    body_key: str = "",
    text_params: dict | None = None,
    target_id: object = "",
    recipient_user=None,
    source_type: str = "",
    source_id: object = "",
    dedup_key: str = "",
    level: str | None = None,
) -> Notification | None:
    organization = context.organization
    if dedup_key and Notification.objects.filter(
        organization=organization, dedup_key=dedup_key, created_at__gte=timezone.now() - timedelta(hours=24)
    ).exists():
        return None
    meta = TYPE_META.get(type, {})
    target_route = meta.get("route", "")
    notification = Notification.objects.create(
        organization=organization,
        type=type,
        audience=audience,
        audience_group=audience_group,
        title=title,
        body=body,
        title_key=title_key,
        body_key=body_key,
        text_params=text_params or {},
        level=level or meta.get("level", NotificationLevel.INFO),
        target_route=target_route,
        target_id=str(target_id) if target_id else "",
        recipient_user=recipient_user,
        source_type=source_type,
        source_id=str(source_id) if source_id else "",
        dedup_key=dedup_key,
    )
    # Доставка в мессенджеры (привязанные сотрудники) — асинхронно через outbox.
    enqueue_event(
        DomainEvent(
            aggregate_type="Notification",
            aggregate_id=str(notification.id),
            event_type=NOTIFICATION_CREATED,
            payload={"notificationId": notification.id},
            tenant_context=context,
        )
    )
    return notification


def notify_management(*, context, dedup_key: str = "", **notification_data) -> int:
    """Create direct notifications for every active OWNER and ADMIN."""

    memberships = OrganizationMembership.objects.filter(
        organization=context.organization,
        role__in=[EmployeeRole.OWNER, EmployeeRole.ADMIN],
        blocked_at__isnull=True,
        user__is_active=True,
    ).select_related("user")
    created = 0
    for membership in memberships:
        notification = notify(
            context=context,
            audience=NotificationAudience.USER,
            recipient_user=membership.user,
            dedup_key=(f"{dedup_key}:user:{membership.user_id}" if dedup_key else ""),
            **notification_data,
        )
        created += notification is not None
    return created


# Маршруты, которыми уведомление ссылается на диалог. Кроме нынешнего «chat»
# здесь старые значения: они лежат в уже созданных строках, и открытый диалог
# обязан гасить и их тоже.
CONVERSATION_ROUTES = ("chat", "salesDialogs", "conversations")


def mark_read(
    *,
    context,
    ids: list[int] | None = None,
    all_unread: bool = False,
    conversation_id: int | None = None,
) -> int:
    """Отметить уведомления прочитанными: перечисленные, все или про диалог.

    Про диалог — потому что открытый диалог и есть прочтение: оклик «клиент
    ждёт» бессмысленно висеть непрочитанным, когда сотрудник уже в переписке.
    Гасятся все уведомления об этом диалоге, а не только те, что клиент успел
    загрузить в шторку.
    """
    queryset = unread_for(context)
    if conversation_id is not None:
        queryset = queryset.filter(
            target_route__in=CONVERSATION_ROUTES, target_id=str(conversation_id)
        )
    elif not all_unread:
        queryset = queryset.filter(id__in=ids or [])
    rows = [
        NotificationRead(
            organization=context.organization,
            notification=notification,
            user=context.actor_user,
        )
        for notification in queryset
    ]
    NotificationRead.objects.bulk_create(rows, ignore_conflicts=True)
    if rows:
        # Счётчик непрочитанных живёт в шапке каждой открытой вкладки: без
        # события они разъезжаются до следующего опроса.
        notify_notifications_changed([context.actor_user.id])
    return len(rows)
