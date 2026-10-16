"""Current team grants shared by reports, ratings and quality results."""

from dataclasses import dataclass

from rest_framework.exceptions import PermissionDenied

from chatballs.conversations.models import Conversation
from chatballs.i18n import t
from chatballs.identity.models import EmployeeRole, OrganizationMembership
from chatballs.identity.policy import MANAGEMENT_ROLES
from chatballs.identity.work_status_services import own_membership


@dataclass(frozen=True)
class ManagementScope:
    actor: OrganizationMembership
    group_ids: tuple[int, ...] | None

    def conversations(self):
        rows = Conversation.objects.filter(organization_id=self.actor.organization_id)
        return rows if self.group_ids is None else rows.filter(group_id__in=self.group_ids)

    def members(self):
        rows = OrganizationMembership.objects.filter(
            organization_id=self.actor.organization_id,
        ).select_related("user")
        return rows if self.group_ids is None else rows.filter(
            group_links__group_id__in=self.group_ids,
        ).distinct()

    def staff_ids(self):
        return set(self.members().values_list("user_id", flat=True))


def management_scope(context, *, forbidden_key):
    actor = own_membership(context=context)
    if actor.role in MANAGEMENT_ROLES:
        return ManagementScope(actor, None)
    if actor.role == EmployeeRole.SUPERVISOR:
        groups = tuple(actor.supervision_links.filter(
            organization_id=context.organization_id,
        ).values_list("group_id", flat=True))
        return ManagementScope(actor, groups)
    raise PermissionDenied(t(forbidden_key))
