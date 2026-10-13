"""Current reply authorization shared by assistance HTTP, worker and realtime."""

from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from chatballs.conversations.access import has_active_participation, has_independent_work_access
from chatballs.conversations.models import ControlMode, Conversation, LifecycleState
from chatballs.conversations.selectors import conversation_is_visible
from chatballs.i18n import t
from chatballs.identity.models import OrganizationMembership
from chatballs.identity.policy import MANAGEMENT_ROLES, require_capability


def may_reply(member, conversation):
    if member is None or member.organization_id != conversation.organization_id:
        return False
    return (
        require_capability(member, "conversations.operate", conversation)
        and conversation_is_visible(actor=member, conversation=conversation)
        and (member.role in MANAGEMENT_ROLES
             or conversation.assigned_operator_id == member.user_id
             or (conversation.control_mode == ControlMode.HUMAN
                 and has_active_participation(member, conversation))
             or (has_independent_work_access(member, conversation)
                 and conversation.control_mode != ControlMode.HUMAN
                 and conversation.assigned_operator_id is None))
    )


def reply_context(context, conversation_id):
    """Caller holds tenant_atomic; lock before checking mutable conversation rights."""
    conversation = Conversation.objects.select_for_update(of=("self",)).select_related(
        "channel__ai_agent", "contact", "connection",
    ).filter(pk=conversation_id, organization_id=context.organization_id).first()
    if conversation is None:
        raise NotFound(t("conversations.not_found"))
    # Membership may be revoked while this operation waits for the conversation lock.
    member = OrganizationMembership.objects.select_related("user", "organization").filter(
        pk=context.membership_id, organization_id=context.organization_id,
        blocked_at__isnull=True, user__is_active=True,
    ).first()
    if not may_reply(member, conversation):
        raise PermissionDenied(t("conversations.unavailable"))
    if conversation.lifecycle != LifecycleState.OPEN:
        raise ValidationError(t("conversations.closed"))
    return member, conversation
