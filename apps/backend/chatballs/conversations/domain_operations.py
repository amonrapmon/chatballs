"""Transaction and retry boundary for existing operator services."""

from functools import wraps
from uuid import UUID, uuid4

from rest_framework.exceptions import ValidationError

from chatballs.conversations.access import require_conversation_action
from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.domain_events import (
    is_accepted,
    record_fact,
    record_public_reply,
)
from chatballs.conversations.models import Conversation, Message
from chatballs.i18n import t
from chatballs.tenancy.database import tenant_atomic


def domain_operation(action, *, capability="conversations.operate"):
    def decorate(function):
        @wraps(function)
        def execute(*, context, operation_id=None, **kwargs):
            try:
                operation_id = UUID(str(operation_id)) if operation_id else uuid4()
            except (ValueError, TypeError, AttributeError) as error:
                raise ValidationError(t("transfers.operation_invalid")) from error
            with tenant_atomic(context):
                conversation_id = kwargs.get("conversation_id") or kwargs["conversation"].pk
                conversation = Conversation.objects.select_for_update().get(
                    pk=conversation_id, organization_id=context.organization_id,
                )
                if capability is not None:
                    require_conversation_action(context, conversation, capability)
                if "conversation" in kwargs:
                    # Existing locked callers (including call creation) rely on
                    # the supplied instance reflecting the successful claim.
                    kwargs["conversation"].refresh_from_db()
                    conversation = kwargs["conversation"]
                actor = context.actor_user
                events = ConversationEvent.objects.filter(
                    organization_id=context.organization_id, operation_id=operation_id,
                )
                prior = events.first()
                if prior:
                    if (prior.conversation_id != conversation.pk
                            or prior.initiated_by_id != (actor.pk if actor else None)
                            or not events.filter(event_type__in=
                                                 {"ASSIGNED", "TRANSFERRED"} if action == "ASSIGNED" else {action}).exists()):
                        raise ValidationError(t("transfers.operation_invalid"))
                    if action == "PUBLIC_REPLY":
                        message = Message.objects.get(
                            conversation=conversation, external_id=f"operation:{operation_id}",
                        )
                        if "text" in kwargs and message.text != kwargs["text"]:
                            raise ValidationError(t("transfers.operation_invalid"))
                        return message
                    if action == "ASSIGNED" and prior.responsible_id != (
                        kwargs["assignee"].pk if kwargs["assignee"] else None
                    ):
                        raise ValidationError(t("transfers.operation_invalid"))
                    return conversation
                accepted = is_accepted(conversation) if action == "ACCEPTED" else False
                before = (conversation.waiting_since, conversation.assigned_operator_id)
                if "conversation" in kwargs:
                    kwargs["conversation"] = conversation
                result = function(context=context, **kwargs)
                conversation.refresh_from_db()
                common = {
                    "operation_id": operation_id, "actor_kind": "HUMAN" if actor else "SYSTEM",
                    "initiated_by_id": actor.pk if actor else None,
                }
                if before[0] is not None and conversation.waiting_since is None:
                    record_fact(conversation, "QUEUE_EXITED", responsible_id=before[1], **common)
                if before[0] is None and conversation.waiting_since is not None:
                    record_fact(conversation, "QUEUE_ENTERED",
                                responsible_id=conversation.assigned_operator_id, **common)
                if before[1] != conversation.assigned_operator_id:
                    # Closing/returning ends responsibility; it is not an assignment.
                    if action in {"ASSIGNED", "ACCEPTED"}:
                        record_fact(conversation, "TRANSFERRED" if before[1] else "ASSIGNED",
                                    responsible_id=conversation.assigned_operator_id, **common)
                if action == "ACCEPTED" and not accepted:
                    record_fact(conversation, action,
                                responsible_id=conversation.assigned_operator_id, **common)
                if action == "CLOSED":
                    record_fact(conversation, action, responsible_id=before[1], **common)
                if action == "PUBLIC_REPLY":
                    result.external_id = f"operation:{operation_id}"
                    result.save(update_fields=["external_id"])
                    record_public_reply(result, operation_id=operation_id)
                return result
        return execute
    return decorate
