"""Transfer validation, replay snapshots and facts inside assignment's transaction."""

from uuid import UUID

from rest_framework.exceptions import APIException, ValidationError

from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.domain_events import record_fact
from chatballs.conversations.transfer_models import ConversationTransfer
from chatballs.conversations.transfer_services import record_transfer
from chatballs.i18n import t


class AssignmentConflict(APIException):
    status_code = 409
    default_code = "assignment_conflict"

    def __init__(self, conversation):
        super().__init__({
            "detail": t("transfers.version_conflict"),
        })
        self.detail.update({
            "assignmentVersion": conversation.assignment_version,
            "assignedOperatorId": conversation.assigned_operator_id,
        })


def transfer_input(data):
    fields = {"userId", "reasonId", "comment", "expectedVersion", "operationId"}
    if not isinstance(data, dict) or set(data) != fields:
        raise ValidationError(t("transfers.fields_required"))
    if any(type(data[field]) is not int or data[field] <= 0 for field in ("userId", "reasonId")):
        raise ValidationError(t("transfers.fields_required"))
    if type(data["expectedVersion"]) is not int or data["expectedVersion"] < 0:
        raise ValidationError(t("transfers.version_invalid"))
    if not isinstance(data["comment"], str):
        raise ValidationError(t("transfers.comment_invalid"))
    try:
        return {**data, "operationId": UUID(str(data["operationId"]))}
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError(t("transfers.operation_invalid")) from error


def replay_transfer(context, conversation, data):
    original = ConversationTransfer.objects.filter(
        organization_id=context.organization_id, operation_id=data["operationId"],
    ).first()
    if original is not None:
        if original.conversation_id != conversation.pk or original.initiated_by_id != context.actor_user.pk:
            raise AssignmentConflict(conversation)
        return original
    if ConversationEvent.objects.filter(
        organization_id=context.organization_id, operation_id=data["operationId"],
    ).exists():
        raise AssignmentConflict(conversation)
    if data["expectedVersion"] != conversation.assignment_version:
        raise AssignmentConflict(conversation)
    if data["userId"] == conversation.assigned_operator_id:
        raise ValidationError(t("transfers.same_recipient"))
    return None


def journal_transfer(context, conversation, data):
    return record_transfer(
        context=context, conversation_id=conversation.pk,
        previous_operator_id=conversation.assigned_operator_id,
        new_operator_id=data["userId"], reason_id=data["reasonId"],
        comment=data["comment"], operation_id=data["operationId"],
    )


def finish_transfer(context, conversation, row):
    row.assignment_version = conversation.assignment_version
    row.save(update_fields=["assignment_version"])
    record_fact(
        conversation, "TRANSFERRED" if row.previous_operator_id else "ASSIGNED",
        actor_kind="HUMAN", initiated_by_id=context.actor_user.pk,
        responsible_id=conversation.assigned_operator_id,
        operation_id=row.operation_id,
    )
    return row


def transfer_payload(row):
    return {
        "id": row.pk, "conversationId": row.conversation_id,
        "operationId": str(row.operation_id), "assignmentVersion": row.assignment_version,
        "initiatedById": row.initiated_by_id, "previousOperatorId": row.previous_operator_id,
        "newOperatorId": row.new_operator_id, "occurredAt": row.occurred_at.isoformat(),
        "reason": {"id": row.reason_id, "code": row.reason_code, "name": row.reason_name},
        "comment": row.comment,
    }
