from uuid import UUID

from django.db import transaction
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from chatballs.conversations.domain_events import is_accepted, operation_key
from chatballs.conversations.models import ControlMode, Conversation
from chatballs.conversations.reply_access import lock_for_reply, require_human_reply
from chatballs.conversations.services import ClaimError, claim_conversation
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.i18n import t


def claim_for_reply(view: ConversationViewBase, request: Request, conversation: Conversation) -> Conversation | Response:
    """Одно действие взятия (дизайн-базлайн v2, решение 2; ADR-CHATBALLS-0003): первая
    реплика сотрудника (текст или файл) атомарно перехватывает диалог у
    AI/очереди. Возвращает диалог или готовый ответ с ошибкой."""
    if request.headers.get("Idempotency-Key"):
        try:
            UUID(request.headers["Idempotency-Key"])
        except ValueError as error:
            raise ValidationError(t("transfers.operation_invalid")) from error
    try:
        conversation = lock_for_reply(context=request.tenant_context, conversation_id=conversation.pk)
    except Conversation.DoesNotExist:
        return Response({"detail": t("conversations.not_found")}, status=404)
    if conversation.control_mode != ControlMode.HUMAN or (
        conversation.assigned_operator_id == request.user.pk and not is_accepted(conversation)
    ):
        try:
            with transaction.atomic():
                conversation = claim_conversation(
                    context=request.tenant_context, conversation_id=conversation.id, operation_id=(operation_key("reply-claim", request.headers["Idempotency-Key"])
                                  if request.headers.get("Idempotency-Key") else None)
                )
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        except ClaimError as error:
            return Response({"detail": str(error)}, status=409)
        view._audit(request, "claimed", conversation)
    try:
        require_human_reply(context=request.tenant_context, conversation=conversation)
    except Conversation.DoesNotExist:
        return Response({"detail": t("conversations.not_found")}, status=404)
    except ClaimError as error:
        return Response({"detail": str(error)}, status=409)
    return conversation
