from django.db import transaction
from django.utils import timezone

from chatballs.conversations.access import require_conversation_action
from chatballs.conversations.assignment_policy import assignment_recipient, policy_for
from chatballs.conversations.domain_operations import domain_operation
from chatballs.conversations.models import (
    Conversation,
    Message,
    MessageAuthor,
    SystemEvent,
)
from chatballs.conversations.transfer_transition import (
    finish_transfer,
    journal_transfer,
    replay_transfer,
    transfer_input,
)
from chatballs.i18n import t
from chatballs.notifications.models import NotificationAudience, NotificationType
from chatballs.notifications.services import notify
from chatballs.tenancy.context import TenantActorKind, TenantContext
from chatballs.tenancy.database import tenant_atomic


def assign_operator(*, context: TenantContext, conversation_id: int, assignee=None,
                    transfer=None, operation_id=None):
    with tenant_atomic(context):
        if transfer is None:
            return _assign_legacy_operator(
                context=context, conversation_id=conversation_id, assignee=assignee,
                operation_id=operation_id,
            )
        return _assign_operator(context, conversation_id, assignee, transfer)


@domain_operation("ASSIGNED", capability="conversations.assign")
def _assign_legacy_operator(*, context, conversation_id, assignee):
    return _assign_operator(context, conversation_id, assignee, None)


def _assign_operator(context, conversation_id, assignee, transfer):
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
    policy = policy_for(context, lock=True) if transfer is not None or assignee is not None else None
    data = transfer_input(transfer) if transfer is not None else None
    if data is not None:
        original = replay_transfer(context, conversation, data)
        if original is not None:
            return original
        assignee = assignment_recipient(context=context, user_id=data["userId"], policy=policy)
    elif assignee is not None:
        assignee = assignment_recipient(context=context, user_id=assignee.pk, policy=policy)
    _require_open(conversation)
    if data is None and conversation.assigned_operator_id == (assignee.pk if assignee else None):
        return conversation
    row = journal_transfer(context, conversation, data) if data is not None else None
    conversation.assigned_operator = assignee
    conversation.assigned_at = timezone.now() if assignee is not None else None
    conversation.save(update_fields=["assigned_operator", "assigned_at"])
    if row is not None:
        finish_transfer(context, conversation, row)
    if assignee is None:
        return conversation
    Message.objects.create(
        conversation=conversation,
        author_type=MessageAuthor.SYSTEM,
        system_event=SystemEvent.ASSIGNED_TO,
        system_params={"operator": operator_label(assignee), **({"transferId": row.pk} if row else {})},
        text="",
    )
    # Себе назначил — сам и знает.
    if row is None and context.actor_user is not None and assignee.pk == context.actor_user.pk:
        return conversation
    contact_name = getattr(conversation.contact, "name", "") or t("conversations.guest")
    notify(
        context=TenantContext.for_resource(
            context.organization, actor_kind=TenantActorKind.SYSTEM,
            correlation_id=context.correlation_id,
        ),
        type=NotificationType.DIALOG_ASSIGNED,
        audience=NotificationAudience.USER,
        recipient_user=assignee,
        title="" if row else t("notifications.assigned_to_you", contact=contact_name),
        title_key="transfers.notification" if row else "notifications.assigned_to_you",
        text_params={"transferId": row.pk} if row else {"contact": contact_name},
        target_id=conversation.id,
        source_type="Conversation",
        source_id=conversation.id,
        dedup_key=f"transfer:{row.operation_id}" if row else f"assign:{conversation.id}:{assignee.pk}",
    )
    return row if row is not None else conversation


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
