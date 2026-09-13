"""Кому адресовано уведомление.

Ответ нужен двум транспортам сразу — сокету открытого приложения и боту в
мессенджере, — поэтому он считается здесь один раз, а не в каждом из них.

Раньше получатели искались перебором: для каждого сотрудника организации
выполнялся отдельный запрос `visible_for(...).exists()`. На сотню рабочих мест
это сотня запросов на каждое входящее сообщение — терпимо, только пока
уведомления доставляются раз в пятнадцать секунд. Здесь два запроса независимо
от размера организации: право выводится из роли, членство в группе — одним
IN-условием.
"""

from __future__ import annotations

from django.db.models import Q

from chatballs.identity.models import OrganizationMembership
from chatballs.identity.policy import MANAGEMENT_ROLES, roles_with_capability
from chatballs.notifications.models import Notification, NotificationAudience

# Аудитория — это право её читать. Зеркало notifications.selectors.visible_for:
# расходиться этим двум таблицам нельзя, иначе уведомление придёт тому, кто его
# потом не увидит в списке, или наоборот.
AUDIENCE_CAPABILITY = {
    NotificationAudience.ALL: "company.view",
    NotificationAudience.OPERATORS: "conversations.view",
    NotificationAudience.OWNER: "employees.manage_privileged",
}


def audience_user_ids(
    *,
    organization_id: int,
    audience: str,
    group_id: int | None = None,
    recipient_user_id: int | None = None,
) -> list[int]:
    """Кого охватывает такая аудитория.

    Отдельно от уведомления, потому что спросить это нужно и до него: очередь
    выясняет, есть ли вообще кому заметить ждущий диалог, ещё не решив, звать ли.
    """
    if audience == NotificationAudience.USER:
        return [recipient_user_id] if recipient_user_id else []
    capability = AUDIENCE_CAPABILITY.get(audience)
    if capability is None:
        return []
    memberships = OrganizationMembership.objects.filter(
        organization_id=organization_id,
        role__in=roles_with_capability(capability),
        blocked_at__isnull=True,
        user__is_active=True,
    )
    if group_id is not None:
        # Та же граница, что у диалога: руководство видит всё, остальные — свою
        # группу (chatballs.identity.policy.conversation_visibility).
        memberships = memberships.filter(
            Q(role__in=MANAGEMENT_ROLES) | Q(group_links__group_id=group_id)
        ).distinct()
    return list(memberships.values_list("user_id", flat=True))


def recipient_user_ids(notification: Notification) -> list[int]:
    """Идентификаторы сотрудников, которым это уведомление адресовано."""
    return audience_user_ids(
        organization_id=notification.organization_id,
        audience=notification.audience,
        group_id=notification.audience_group_id,
        recipient_user_id=notification.recipient_user_id,
    )
