"""Self-service availability; never driven by presence or dialogue load."""

from uuid import UUID

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from chatballs.i18n import t
from chatballs.identity.models import OrganizationMembership
from chatballs.identity.work_status_codes import WorkStatus
from chatballs.identity.work_status_models import WorkStatusOperation
from chatballs.identity.work_status_realtime import notify_work_status_changed
from chatballs.tenancy.context import TenantActorKind
from chatballs.tenancy.database import tenant_atomic


class WorkStatusVersionConflict(APIException):
    status_code = 409
    default_code = "work_status_version_conflict"

    def __init__(self):
        super().__init__(t("work_status.version_conflict"))


def own_membership(*, context, lock=False):
    """Reload authorization data: a cached context may predate a block."""
    if (
        context.actor_kind != TenantActorKind.HUMAN
        or context.membership is None or context.actor_user is None
        or context.membership.organization_id != context.organization_id
        or context.actor_user.pk != context.membership.user_id
    ):
        raise PermissionDenied(t("work_status.forbidden"))
    memberships = OrganizationMembership.objects.filter(
        pk=context.membership_id, organization_id=context.organization_id,
        user_id=context.actor_user.pk, blocked_at__isnull=True, user__is_active=True,
    )
    if lock:
        memberships = memberships.select_for_update(of=("self",))
    membership = memberships.first()
    if membership is None:
        raise PermissionDenied(t("work_status.forbidden"))
    return membership


def change_work_status(*, context, status, expected_version, operation_id):
    """Return a durable snapshot, including on replay after later transitions.

    Membership locking serializes requests. Version validation happens after
    replay lookup, but before the same-status check. Only actual changes increment
    the version and start an interval. The database transaction owns both writes.
    """
    try:
        operation_id = UUID(str(operation_id))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError(t("work_status.operation_invalid")) from error
    if status not in WorkStatus.values:
        raise ValidationError(t("work_status.status_invalid"))
    if type(expected_version) is not int or expected_version < 0:
        raise ValidationError(t("work_status.version_invalid"))
    with tenant_atomic(context):
        membership = own_membership(context=context, lock=True)
        operations = WorkStatusOperation.objects.filter(
            organization_id=context.organization_id, membership=membership,
        )
        original = operations.filter(operation_id=operation_id).first()
        if original is not None:
            return original
        if membership.work_status_version != expected_version:
            raise WorkStatusVersionConflict()
        previous_status = membership.work_status
        now = timezone.now()
        if previous_status != status:
            membership.work_status = status
            membership.work_status_version += 1
            membership.work_status_changed_at = now
            membership.save(update_fields=[
                "work_status", "work_status_version", "work_status_changed_at",
            ])
        operation = WorkStatusOperation.objects.create(
            organization_id=context.organization_id, membership=membership,
            operation_id=operation_id, previous_status=previous_status, status=status,
            version=membership.work_status_version,
            changed_at=membership.work_status_changed_at, recorded_at=now,
        )
        if operation.changed:
            transaction.on_commit(lambda: notify_work_status_changed(
                context.organization_id, membership.user_id,
            ))
        return operation


def own_work_status_history(*, context):
    """Materialize transitions while the tenant transaction remains active."""
    with tenant_atomic(context):
        membership = own_membership(context=context)
        return list(WorkStatusOperation.objects.filter(
            organization_id=context.organization_id, membership=membership,
        ).exclude(previous_status=F("status")))
