from django.db import transaction
from django.utils import timezone

from chatballs.conversations.access import require_conversation_action
from chatballs.conversations.models import (
    Conversation,
    Message,
    MessageAuthor,
    SystemEvent,
)
from chatballs.i18n import t
from chatballs.notifications.models import NotificationAudience, NotificationType
from chatballs.notifications.services import notify
from chatballs.tenancy.context import TenantContext


@transaction.atomic
def assign_operator(*, context: TenantContext, conversation_id: int, assignee) -> Conversation:
    """Назначить ответственного за диалог (или снять назначение).

    Назначение — не взятие: человек ещё не ответил и мог даже не увидеть
    диалог. Но из общей очереди диалог уходит — отвечать в нём, кроме
    назначенного и руководства, уже никто не может, — поэтому назначенного надо
    позвать лично и поставить срок. Не успел — диалог возвращается в общую
    очередь (chatballs.conversations.escalation).

    Раньше эта операция молча писала внешний ключ: назначенный не узнавал,
    диалог продолжал числиться в общей очереди, а взять его оттуда было уже
    нельзя.
    """
    from chatballs.conversations.services import _require_open, operator_label

    conversation = Conversation.objects.select_for_update().get(
        id=conversation_id, organization=context.organization
    )
    require_conversation_action(context, conversation, "conversations.assign")
    from chatballs.identity.models import OrganizationMembership

    if assignee is not None and not OrganizationMembership.objects.filter(
        organization_id=context.organization_id, user_id=assignee.pk,
        blocked_at__isnull=True, user__is_active=True,
    ).exists():
        raise Conversation.DoesNotExist
    _require_open(conversation)
    conversation.assigned_operator = assignee
    conversation.assigned_at = timezone.now() if assignee is not None else None
    conversation.save(update_fields=["assigned_operator", "assigned_at"])
    if assignee is None:
        return conversation
    Message.objects.create(
        conversation=conversation,
        author_type=MessageAuthor.SYSTEM,
        system_event=SystemEvent.ASSIGNED_TO,
        system_params={"operator": operator_label(assignee)},
        text="",
    )
    # Себе назначил — сам и знает.
    if context.actor_user is not None and assignee.pk == context.actor_user.pk:
        return conversation
    contact_name = getattr(conversation.contact, "name", "") or t("conversations.guest")
    notify(
        context=context,
        type=NotificationType.DIALOG_ASSIGNED,
        audience=NotificationAudience.USER,
        recipient_user=assignee,
        title=t("notifications.assigned_to_you", contact=contact_name),
        title_key="notifications.assigned_to_you",
        text_params={"contact": contact_name},
        target_id=conversation.id,
        source_type="Conversation",
        source_id=conversation.id,
        dedup_key=f"assign:{conversation.id}:{assignee.pk}",
    )
    return conversation


@transaction.atomic
def move_conversation(*, context, conversation_id, group):
    conversation = Conversation.objects.select_for_update().get(
        pk=conversation_id, organization_id=context.organization_id,
    )
    require_conversation_action(context, conversation, "conversations.transfer")
    if group is not None and group.organization_id != context.organization_id:
        raise Conversation.DoesNotExist
    conversation.group = group
    conversation.save(update_fields=["group"])
    return conversation
