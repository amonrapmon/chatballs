"""Current report rights; historical dimensions never grant access."""

from rest_framework.exceptions import NotFound, PermissionDenied

from chatballs.conversations.management_scope import management_scope
from chatballs.conversations.selectors import visible_conversations_for
from chatballs.i18n import t
from chatballs.identity.models import EmployeeRole, OrganizationMembership
from chatballs.identity.work_status_services import own_membership
from chatballs.tenancy.context import TenantContext


def report_scope(context, filters):
    actor = own_membership(context=context)
    context = TenantContext.for_membership(actor)
    conversations = visible_conversations_for(context).order_by().prefetch_related(None).select_related(None)
    members = OrganizationMembership.objects.filter(organization_id=context.organization_id).select_related("user")
    if actor.role == EmployeeRole.EMPLOYEE:
        members = members.filter(pk=actor.pk)
        if filters.employee != actor.user_id:
            raise PermissionDenied(t("support_stats.own_only"))
    else:
        scope = management_scope(context, forbidden_key="support_stats.forbidden")
        conversations = conversations.filter(pk__in=scope.conversations().values("pk"))
        members = scope.members()
        if scope.group_ids is not None and filters.group is not None and filters.group not in scope.group_ids:
            raise NotFound(t("support_stats.filter_unavailable"))
    if filters.employee is not None and not members.filter(user_id=filters.employee).exists():
        raise NotFound(t("support_stats.filter_unavailable"))
    # Dimension IDs may survive removal in the immutable journal. Validate them
    # against visible facts too, without revealing whether a foreign ID exists.
    for key, field in (("group", "group_id"), ("connection", "connection_id")):
        value = getattr(filters, key)
        if value is not None and not (
            conversations.filter(**{field: value}).exists()
            or conversations.filter(domain_events__organization_id=context.organization_id,
                                    **{f"domain_events__{field}": value}).exists()
        ):
            raise NotFound(t("support_stats.filter_unavailable"))
    if filters.employee is not None:
        members = members.filter(user_id=filters.employee)
    return context, conversations, list(members.order_by("user_id"))
