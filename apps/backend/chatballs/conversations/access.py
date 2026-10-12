"""Ordinary work and explicit supervision are independent grants (ADR-0033)."""

from django.db.models import Q

from chatballs.identity.group_models import member_group_ids
from chatballs.identity.models import EmployeeRole, OrganizationMembership

ACTION_CAPABILITIES = {
    "conversations.assign": "conversations.operate",
    "conversations.transfer": "conversations.operate",
    "conversations.participants": "conversations.operate",
    "conversations.comment": "conversations.operate",
}
SUPERVISION_CAPABILITIES = frozenset({"conversations.view", *ACTION_CAPABILITIES})


def visibility_predicate(scope):
    from chatballs.conversations.participant_models import ConversationParticipant

    groups = scope["group_ids"] | scope["supervised_group_ids"]
    return (
        Q(group__isnull=True) | Q(group_id__in=groups)
        | Q(assigned_operator_id=scope["user_id"])
        | Q(pk__in=ConversationParticipant.objects.active().filter(
            membership_id=scope["membership_id"],
        ).values("conversation_id"))
    )


def has_work_access(profile, conversation):
    return (
        conversation.group_id is None
        or conversation.group_id in member_group_ids(profile)
        or conversation.assigned_operator_id == profile.user_id
        or conversation.participants.active().filter(membership_id=profile.pk).exists()
    )


def has_control_access(profile, conversation):
    return (
        profile.role == EmployeeRole.SUPERVISOR
        and conversation.group_id is not None
        and profile.supervision_links.filter(group_id=conversation.group_id).exists()
    )


def authorize_conversation(profile, capability, conversation):
    from chatballs.identity.policy import MANAGEMENT_ROLES, _role_capabilities

    if profile.organization_id != conversation.organization_id:
        return False
    base_capability = ACTION_CAPABILITIES.get(capability, capability)
    if base_capability not in _role_capabilities(profile.role):
        return False
    if profile.role in MANAGEMENT_ROLES or has_work_access(profile, conversation):
        return True
    return capability in SUPERVISION_CAPABILITIES and has_control_access(profile, conversation)


def require_conversation_action(context, conversation, capability):
    from chatballs.conversations.models import Conversation
    from chatballs.identity.policy import require_capability

    current = Conversation.objects.filter(
        pk=conversation.pk, organization_id=context.organization_id,
    ).first()
    if (
        current is None
        or context.actor_user is None or context.membership is None
        or context.actor_user.pk != context.membership.user_id
        or context.organization_id != conversation.organization_id
        or not require_capability(context.membership, capability, current)
    ):
        raise Conversation.DoesNotExist


def conversation_access_payload(conversation, viewer_id):
    from chatballs.identity.policy import MANAGEMENT_ROLES, _role_capabilities

    actor = OrganizationMembership.objects.filter(
        organization_id=conversation.organization_id, user_id=viewer_id,
        blocked_at__isnull=True, user__is_active=True,
    ).first() if viewer_id else None
    profile = actor
    if profile is None:
        return {"actions": [], "supervised": False}
    actions = {"conversations.view", "conversations.operate", "conversations.call", *ACTION_CAPABILITIES}
    supervised = has_control_access(profile, conversation)
    ordinary = profile.role in MANAGEMENT_ROLES or has_work_access(profile, conversation)
    base = _role_capabilities(profile.role)
    return {
        "actions": sorted(action for action in actions
                          if ACTION_CAPABILITIES.get(action, action) in base
                          and (ordinary or supervised and action in SUPERVISION_CAPABILITIES)),
        "supervised": supervised,
    }
