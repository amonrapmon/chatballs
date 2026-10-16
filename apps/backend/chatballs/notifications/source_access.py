"""Authorize notification sources at read and delivery time, not creation time."""

from django.db.models import CharField, Q
from django.db.models.functions import Cast

from chatballs.conversations.models import Conversation
from chatballs.conversations.selectors import visible_conversations_for
from chatballs.identity.models import EmployeeRole, OrganizationMembership
from chatballs.identity.policy import MANAGEMENT_ROLES, roles_with_capability


def filter_notification_sources(queryset, context):
    visible_ids = visible_conversations_for(context).annotate(
        string_id=Cast("id", output_field=CharField()),
    ).values("string_id")
    return queryset.filter(~Q(source_type="Conversation") | Q(source_id__in=visible_ids))


def notification_recipient_ids(notification, audience_ids):
    if notification.source_type != "Conversation":
        return audience_ids
    try:
        source_id = int(notification.source_id)
    except (ValueError, TypeError):
        return []
    conversation = Conversation.objects.filter(
        pk=source_id, organization_id=notification.organization_id,
    ).first()
    if conversation is None:
        return []
    profiles = OrganizationMembership.objects.filter(
        organization_id=notification.organization_id,
        blocked_at__isnull=True, user__is_active=True,
        role__in=roles_with_capability("conversations.view"),
    )
    # A stored audience group may be obsolete after moving the conversation.
    if notification.audience == "USER":
        profiles = profiles.filter(user_id=notification.recipient_user_id)
    elif notification.audience != "OPERATORS":
        profiles = profiles.filter(user_id__in=audience_ids)
    if conversation.group_id is not None:
        profiles = profiles.filter(
            Q(role__in=MANAGEMENT_ROLES)
            | Q(group_links__group_id=conversation.group_id)
            | Q(role=EmployeeRole.SUPERVISOR, supervision_links__group_id=conversation.group_id)
            | Q(user_id=conversation.assigned_operator_id)
            | Q(conversation_participations__conversation_id=conversation.pk,
                conversation_participations__left_at__isnull=True)
        )
    return list(profiles.distinct().values_list("user_id", flat=True))
