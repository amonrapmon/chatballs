"""Кого зовёт правило и как: коды получателей превращаются в сотрудников.

Код из настройки — только круг, из которого выбирают. Попадёт ли в него
сотрудник, решает его нынешний доступ к этому диалогу: уволенный, заблокированный,
вышедший из группы и супервизор без этой группы в области контроля оклика не
получат. Рабочая доступность учитывается, только если правило просит об этом
явно, и к присутствию за экраном отношения не имеет.

Оклик уходит штатным механизмом уведомлений, лично каждому: так его доставка в
браузер и в мессенджер, подписки и повторная проверка доступа при доставке
остаются такими же, как у остальных уведомлений.
"""

from __future__ import annotations

from django.db.models import Q

from chatballs.conversations.access import authorize_conversation
from chatballs.conversations.models import Conversation
from chatballs.conversations.rules.conditions import available_only
from chatballs.conversations.rules.models import (
    HandlingRule,
    RuleExecution,
    RuleExecutionReason,
    RuleRecipient,
)
from chatballs.conversations.rules.scheduler import SkipAction
from chatballs.i18n import customer_language, t
from chatballs.identity.models import EmployeeRole, OrganizationMembership
from chatballs.identity.policy import MANAGEMENT_ROLES, roles_with_capability
from chatballs.identity.work_status_codes import WorkStatus
from chatballs.notifications.models import (
    NotificationAudience,
    NotificationLevel,
    NotificationType,
)
from chatballs.notifications.services import notify
from chatballs.tenancy.context import TenantContext

_VIEW = "conversations.view"


def _circle(rule: HandlingRule, conversation: Conversation) -> Q | None:
    """Круг получателей по кодам настройки. None — звать некого."""
    codes = set(rule.recipients)
    group_id = conversation.group_id
    parts: list[Q] = []
    if RuleRecipient.ASSIGNEE in codes and conversation.assigned_operator_id:
        parts.append(Q(user_id=conversation.assigned_operator_id))
    if RuleRecipient.CONVERSATION_GROUP in codes:
        # Диалог без группы виден всем, кто работает с диалогами.
        parts.append(Q(group_links__group_id=group_id) if group_id else Q(pk__isnull=False))
    if RuleRecipient.GROUP_SUPERVISORS in codes and group_id:
        parts.append(Q(role=EmployeeRole.SUPERVISOR, supervision_links__group_id=group_id))
    if RuleRecipient.MANAGEMENT in codes:
        parts.append(Q(role__in=MANAGEMENT_ROLES))
    if not parts:
        return None
    circle = parts[0]
    for part in parts[1:]:
        circle |= part
    return circle


def recipients_for(rule: HandlingRule, conversation: Conversation) -> list[OrganizationMembership]:
    circle = _circle(rule, conversation)
    if circle is None:
        return []
    profiles = OrganizationMembership.objects.select_related("user").filter(
        organization_id=conversation.organization_id,
        role__in=roles_with_capability(_VIEW),
        blocked_at__isnull=True,
        user__is_active=True,
    )
    if available_only(rule):
        profiles = profiles.filter(work_status=WorkStatus.READY)
    return [
        profile
        for profile in profiles.filter(circle).distinct().order_by("pk")
        if authorize_conversation(profile, _VIEW, conversation)
    ]


def notify_recipients(
    *,
    context: TenantContext,
    conversation: Conversation,
    execution: RuleExecution,
    title_key: str,
) -> dict:
    """Окликнуть получателей правила. Возвращает ссылки для журнала."""
    recipients = recipients_for(execution.rule, conversation)
    if not recipients:
        raise SkipAction(RuleExecutionReason.NO_RECIPIENTS)
    contact = getattr(conversation.contact, "name", "") or t("conversations.guest")
    params = {"contact": contact, "minutes": execution.rule.delay_minutes}
    notifications = [
        notify(
            context=context,
            type=NotificationType.DIALOG_WAITING_LONG,
            audience=NotificationAudience.USER,
            recipient_user=profile.user,
            level=NotificationLevel.WARNING,
            # Запасной текст для мессенджера, где фразу по ключу собрать нечем.
            title=t(title_key, language=customer_language(context.organization), **params),
            title_key=title_key,
            text_params=params,
            target_id=conversation.id,
            source_type="Conversation",
            source_id=conversation.id,
            # Ключ действия и получателя: повтор той же работы второго оклика
            # не создаёт, а у следующего ожидания он свой.
            dedup_key=f"rule-execution:{execution.pk}:user:{profile.user_id}",
        )
        for profile in recipients
    ]
    return {
        "notification": next((item for item in notifications if item is not None), None),
        "recipient_user_ids": [profile.user_id for profile in recipients],
    }
