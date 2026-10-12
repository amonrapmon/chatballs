from uuid import UUID

from django.db import transaction
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response

from chatballs.conversations.domain_events import is_accepted, operation_key
from chatballs.conversations.models import ControlMode, Conversation
from chatballs.conversations.services import ClaimError, claim_conversation
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.i18n import t
from chatballs.identity.policy import ResourceScope, authorize


def claim_for_reply(view: ConversationViewBase, request: Request, conversation: Conversation) -> Conversation | Response:
    """Одно действие взятия (дизайн-базлайн v2, решение 2; ADR-CHATBALLS-0003): первая
    реплика сотрудника (текст или файл) атомарно перехватывает диалог у
    AI/очереди. Возвращает диалог или готовый ответ с ошибкой."""
    if request.headers.get("Idempotency-Key"):
        try:
            UUID(request.headers["Idempotency-Key"])
        except ValueError as error:
            raise ValidationError(t("transfers.operation_invalid")) from error
    if conversation.control_mode != ControlMode.HUMAN or (
        conversation.assigned_operator_id == request.user.pk and not is_accepted(conversation)
    ):
        try:
            with transaction.atomic():
                conversation = claim_conversation(
                    context=request.tenant_context, conversation_id=conversation.id, operation_id=(operation_key("reply-claim", request.headers["Idempotency-Key"])
                                  if request.headers.get("Idempotency-Key") else None)
                )
        except ClaimError as error:
            return Response({"detail": str(error)}, status=409)
        view._audit(request, "claimed", conversation)
    manager_override = authorize(
        request.tenant_context.membership,
        view.required_capability,
        ResourceScope(conversation.organization_id),
    )
    if conversation.assigned_operator_id != request.user.id and not manager_override:
        return Response({"detail": t("conversations.handled_by_other")}, status=409)
    return conversation


