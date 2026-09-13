from django.db.models import Q, QuerySet

from chatballs.identity.policy import (
    ResourceScope,
    authorize,
    conversation_visibility,
)
from chatballs.notifications.models import Notification, NotificationAudience
from chatballs.notifications.recipients import AUDIENCE_CAPABILITY
from chatballs.tenancy.context import TenantContext


def visible_for(context: TenantContext) -> QuerySet[Notification]:
    profile = context.membership
    if profile is None or context.actor_user is None:
        return Notification.objects.none()
    user = context.actor_user
    organization_scope = ResourceScope(profile.organization_id)
    audiences = [
        audience
        for audience, capability in AUDIENCE_CAPABILITY.items()
        if authorize(profile, capability, organization_scope)
    ]
    by_audience = Q(audience__in=audiences)
    scope = conversation_visibility(profile)
    if scope is not None:
        # Уведомление о диалоге группы читает тот же, кому виден сам диалог.
        # Предикат намеренно взят тот же (ADR-CHATBALLS-0043 §4): два разных
        # ответа на вопрос «кому это видно» — дефект, а не гибкость. Раньше
        # уведомления фильтровались только правом, и оператор чужой группы
        # получал оклик с именем клиента и куском переписки по диалогу, который
        # не может открыть.
        by_audience &= Q(audience_group__isnull=True) | Q(
            audience_group_id__in=scope.get("group_ids") or ()
        )
    return Notification.objects.filter(organization_id=profile.organization_id).filter(
        by_audience | Q(audience=NotificationAudience.USER, recipient_user=user)
    )


def unread_for(context: TenantContext) -> QuerySet[Notification]:
    return visible_for(context).exclude(reads__user=context.actor_user)
