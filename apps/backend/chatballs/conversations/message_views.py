from rest_framework.request import Request
from rest_framework.response import Response

from chatballs.conversations.message_history import MESSAGE_WINDOW_SIZE as MESSAGE_WINDOW_SIZE
from chatballs.conversations.models import Conversation
from chatballs.conversations.operator_reply import send_contact_request, send_text_reply
from chatballs.conversations.reply_claim import claim_for_reply as claim_for_reply
from chatballs.conversations.reply_http import reply_response
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.i18n import t


class ConversationMessageView(ConversationViewBase):
    # Читает историю тот, кто видит диалог; пишет — тот, кто его ведёт.
    required_capabilities = {"GET": "conversations.view", "POST": "conversations.operate"}
    required_capability = "conversations.operate"

    def get(self, request: Request, conversation_id: int) -> Response:
        from chatballs.conversations.message_history import message_history

        try:
            conversation = self._conversation(request, conversation_id)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        return Response(message_history(conversation, request.query_params))

    def post(self, request: Request, conversation_id: int) -> Response:
        return reply_response(send_text_reply(
            context=request.tenant_context,
            conversation_id=conversation_id,
            text=request.data.get("text", ""),
            operation_id=request.headers.get("Idempotency-Key"),
            suggestion_id=request.data.get("suggestionId"),
            suggestion_key=request.data.get("operationKey"),
            request=request,
        ))


class ConversationRequestContactView(ConversationViewBase):
    required_capability = "conversations.operate"

    def post(self, request: Request, conversation_id: int) -> Response:
        return reply_response(send_contact_request(
            context=request.tenant_context,
            conversation_id=conversation_id,
            operation_id=request.headers.get("Idempotency-Key"),
            request=request,
        ))
