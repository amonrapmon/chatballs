"""Current membership rights for availability reads and recipient delivery."""

from rest_framework.exceptions import NotFound, PermissionDenied

from chatballs.i18n import t
from chatballs.identity.models import EmployeeRole, OrganizationMembership
from chatballs.identity.policy import can_administer_access, has_capability_any_scope
from chatballs.identity.supervision_models import EmployeeGroupSupervision
from chatballs.identity.work_status_services import own_membership


def directory_memberships(organization_id):
    return OrganizationMembership.objects.select_related("user").filter(
        organization_id=organization_id, blocked_at__isnull=True, user__is_active=True,
    )


def may_read_directory(actor):
    return has_capability_any_scope(actor, "conversations.view")


def readable_membership(*, context, user_id=None):
    actor = own_membership(context=context)
    if user_id is None or user_id == actor.user_id:
        return actor
    targets = OrganizationMembership.objects.filter(organization_id=context.organization_id)
    if actor.role == EmployeeRole.SUPERVISOR:
        groups = EmployeeGroupSupervision.objects.filter(
            organization_id=context.organization_id, employee=actor,
        ).values("group_id")
        targets = targets.filter(group_links__group_id__in=groups)
    elif not can_administer_access(actor):
        raise PermissionDenied(t("work_status.read_forbidden"))
    target = targets.filter(user_id=user_id).first()
    if target is None:
        raise NotFound(t("work_status.member_not_found"))
    return target


def may_receive_change(*, organization_id, membership_id, user_id):
    actor = directory_memberships(organization_id).filter(pk=membership_id).first()
    return (
        actor is not None and may_read_directory(actor)
        and directory_memberships(organization_id).filter(user_id=user_id).exists()
    )
