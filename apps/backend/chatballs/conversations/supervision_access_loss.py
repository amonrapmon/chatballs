"""Own audited revocation for a previously opened conversation; never its content."""

from chatballs.conversations.models import Conversation, ConversationRead
from chatballs.identity.models import AuditEvent, AuditResult, OrganizationMembership


def supervision_access_loss(context, conversation_id):
    if context.membership_id is None or context.actor_user is None:
        return None
    if not OrganizationMembership.objects.filter(
        pk=context.membership_id, organization_id=context.organization_id,
        user_id=context.actor_user.pk, blocked_at__isnull=True, user__is_active=True,
    ).exists():
        return None
    conversation = Conversation.objects.filter(
        pk=conversation_id, organization_id=context.organization_id,
        group__isnull=False, archived_at__isnull=True,
    ).select_related("group").first()
    if conversation is None:
        return None
    read = ConversationRead.objects.filter(
        conversation=conversation, user_id=context.actor_user.pk,
    ).first()
    if read is None:
        return None
    # The event belongs to this employee in this tenant. A URL or another
    # employee's audit cannot serve as evidence of prior supervision.
    event = AuditEvent.objects.filter(
        organization_id=context.organization_id,
        object_type="HumanUser", object_id=str(context.actor_user.pk),
        action="identity.employee_supervised_groups_changed", result=AuditResult.SUCCESS,
        created_at__gte=read.updated_at,
        payload__oldGroupIds__contains=[conversation.group_id],
    ).exclude(payload__groupIds__contains=[conversation.group_id]).select_related("actor").order_by("-created_at", "-id").first()
    if event is None or event.actor is None or conversation.created_at > event.created_at:
        return None
    return {
        "groupId": conversation.group_id,
        "groupName": conversation.group.name,
        "actorName": event.actor.full_name or event.actor.email,
        "occurredAt": event.created_at.isoformat(),
    }
