"""Retry boundary for the existing file and voice HTTP operations."""

from functools import wraps
from uuid import UUID, uuid4

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.domain_events import record_public_reply
from chatballs.conversations.models import Conversation, Message
from chatballs.conversations.reply_access import lock_for_reply, require_human_reply
from chatballs.conversations.serializers import message_payload
from chatballs.conversations.services import ClaimError
from chatballs.i18n import t
from chatballs.tenancy.database import tenant_atomic


def public_media_operation(function):
    @wraps(function)
    def execute(view, request, conversation_id):
        try:
            operation_id = UUID(request.headers["Idempotency-Key"]) if request.headers.get(
                "Idempotency-Key"
            ) else uuid4()
        except ValueError as error:
            raise ValidationError(t("transfers.operation_invalid")) from error
        with tenant_atomic(request.tenant_context):
            try:
                view._conversation(request, conversation_id, view.required_capability)
                conversation = lock_for_reply(
                    context=request.tenant_context, conversation_id=conversation_id,
                )
            except Conversation.DoesNotExist:
                return Response({"detail": t("conversations.not_found")}, status=404)
            prior = ConversationEvent.objects.filter(
                organization_id=request.tenant_context.organization_id,
                operation_id=operation_id,
            ).first()
            if prior:
                try:
                    require_human_reply(context=request.tenant_context, conversation=conversation)
                except Conversation.DoesNotExist:
                    return Response({"detail": t("conversations.not_found")}, status=404)
                except ClaimError as error:
                    return Response({"detail": str(error)}, status=409)
                if (prior.conversation_id != conversation_id
                        or prior.initiated_by_id != request.user.pk
                        or prior.event_type != "PUBLIC_REPLY"):
                    raise ValidationError(t("transfers.operation_invalid"))
                message = Message.objects.get(
                    conversation_id=conversation_id, external_id=f"operation:{operation_id}",
                )
                if message.kind != view.public_reply_kind:
                    raise ValidationError(t("transfers.operation_invalid"))
                return Response({"message": message_payload(message)}, status=201)
            response = function(view, request, conversation_id)
            if response.status_code == 201:
                message = Message.objects.select_related("conversation").get(
                    pk=response.data["message"]["id"], conversation_id=conversation_id,
                )
                message.external_id = f"operation:{operation_id}"
                message.save(update_fields=["external_id"])
                record_public_reply(message, operation_id=operation_id)
            return response
    return execute
