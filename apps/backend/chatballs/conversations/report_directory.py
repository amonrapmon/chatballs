"""Minimal filter identities from the current management area; no admin data."""

from django.db.models import Q

from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.management_scope import management_scope
from chatballs.conversations.selectors import visible_conversations_for
from chatballs.identity.administration_payloads import administration_timezones
from chatballs.identity.avatars import user_avatar_url
from chatballs.identity.employee_availability import employee_availability
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import AuditEvent, AuditResult, EmployeeRole
from chatballs.identity.report_access import report_actions
from chatballs.identity.work_status_services import own_membership
from chatballs.integrations.models import Integration, IntegrationKind
from chatballs.tenancy.database import tenant_atomic


def own_revocation(actor):
    event = AuditEvent.objects.filter(
        organization_id=actor.organization_id, object_type="HumanUser",
        object_id=str(actor.user_id), result=AuditResult.SUCCESS,
    ).filter(
        Q(action="identity.employee_role_changed", payload__oldRole="SUPERVISOR")
        | Q(action="identity.employee_supervised_groups_changed", payload__groupIds=[]),
    ).exclude(
        Q(action="identity.employee_role_changed", payload__role="SUPERVISOR")
        | Q(action="identity.employee_supervised_groups_changed", payload__oldGroupIds=[]),
    ).order_by("-created_at", "-id").first()
    return event.created_at.isoformat() if event else None


def report_directory(context):
    with tenant_atomic(context):
        actor = own_membership(context=context)
        actions = report_actions(actor)
        payload = {
            "actions": actions, "restricted": actor.role == EmployeeRole.SUPERVISOR,
            "revokedAt": None if actions else own_revocation(actor),
            "groups": [], "employees": [], "connections": [],
            "timezone": context.organization.timezone,
            "timezones": administration_timezones(),
        }
        if not actions:
            return payload
        scope = management_scope(context, forbidden_key="support_stats.forbidden")
        groups = EmployeeGroup.objects.filter(organization_id=context.organization_id)
        connections = Integration.objects.filter(
            organization_id=context.organization_id, kind=IntegrationKind.MESSENGER,
        )
        if scope.group_ids is not None:
            groups = groups.filter(pk__in=scope.group_ids)
            conversations = visible_conversations_for(context).filter(
                pk__in=scope.conversations().values("pk"),
            )
            historical = ConversationEvent.objects.filter(
                organization_id=context.organization_id,
                conversation_id__in=conversations.values("pk"),
            ).values("connection_id")
            connections = connections.filter(
                Q(pk__in=conversations.values("connection_id")) | Q(pk__in=historical),
            )
        members = list(scope.members().order_by("user_id"))
        availability = employee_availability(context.organization_id, members)
        payload["groups"] = list(groups.order_by("name", "pk").values("id", "name"))
        payload["connections"] = list(connections.order_by("name", "pk").values("id", "name", "provider"))
        payload["employees"] = [{
            "id": member.user_id, "fullName": member.user.full_name,
            "email": member.user.email, "isBlocked": member.is_blocked,
            "avatarUrl": user_avatar_url(member.user, context.organization.public_id),
            **availability[member.user_id],
        } for member in members]
        return payload
