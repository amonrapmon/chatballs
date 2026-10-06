"""Reason management and a journal writer for the future assignment transaction.

Writing a record does not change the assignee or publish an event. The assignment
workflow must call it in its own transaction with the actual previous assignee.
"""

from uuid import UUID

from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from chatballs.conversations.selectors import conversation_for_context
from chatballs.conversations.transfer_models import ConversationTransfer, TransferReason
from chatballs.i18n import t
from chatballs.identity.models import OrganizationMembership
from chatballs.identity.policy import ResourceScope, authorize


def require_reason_management(context):
    if not authorize(context.membership, "settings.manage", ResourceScope(context.organization_id)):
        raise PermissionDenied(t("transfers.reasons_forbidden"))


def reasons_for_management(context):
    require_reason_management(context)
    return TransferReason.objects.filter(organization_id=context.organization_id)


@transaction.atomic
def save_reason(*, context, data, reason_id=None):
    reasons = reasons_for_management(context)
    if reason_id is None:
        reason = TransferReason(organization_id=context.organization_id)
    else:
        reason = reasons.select_for_update().filter(pk=reason_id).first()
        if reason is None:
            raise NotFound(t("transfers.reason_not_found"))
    for field in ("code", "name", "is_active"):
        if field in data:
            setattr(reason, field, data[field])
    try:
        with transaction.atomic():
            reason.save()
    except IntegrityError as error:
        if getattr(error.__cause__, "diag", None) and error.__cause__.diag.constraint_name == "uniq_transfer_reason_org_code":
            raise ValidationError({"code": t("transfers.reason_code_taken")}) from error
        raise
    return reason


def disable_reason(*, context, reason_id):
    # DELETE is a soft disable even before first use: existing history stays intact.
    return save_reason(context=context, reason_id=reason_id, data={"is_active": False})


@transaction.atomic
def record_transfer(*, context, conversation_id, previous_operator_id,
                    new_operator_id, reason_id, comment, operation_id):
    """Store only internal metadata. No Message, notification payload or AI input."""
    conversation = conversation_for_context(context=context, conversation_id=conversation_id)
    if not authorize(context.membership, "conversations.operate", conversation):
        raise PermissionDenied(t("transfers.record_forbidden"))
    if context.actor_user is None or context.actor_user.pk != context.membership.user_id:
        raise PermissionDenied(t("transfers.record_forbidden"))
    reason = TransferReason.objects.select_for_update().filter(
        organization_id=context.organization_id, pk=reason_id, is_active=True
    ).first()
    if reason is None:
        raise ValidationError(t("transfers.active_reason_required"))
    if new_operator_id is None or not OrganizationMembership.objects.filter(
        organization_id=context.organization_id, user_id=new_operator_id,
        blocked_at__isnull=True, user__is_active=True,
    ).exists():
        raise ValidationError(t("admin.employee_not_found"))
    if not isinstance(comment, str):
        raise ValidationError(t("transfers.comment_invalid"))
    try:
        operation_id = UUID(str(operation_id))
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError(t("transfers.operation_invalid")) from error
    return ConversationTransfer.objects.create(
        organization_id=context.organization_id, conversation=conversation, reason=reason,
        previous_operator_id=previous_operator_id, new_operator_id=new_operator_id,
        initiated_by=context.actor_user, reason_code=reason.code, reason_name=reason.name,
        comment=comment, operation_id=operation_id,
    )
