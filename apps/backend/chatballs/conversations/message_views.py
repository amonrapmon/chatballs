from rest_framework.request import Request
from rest_framework.response import Response

from chatballs.api.pagination import (
    cursor_id,
    window,
    window_payload,
    window_size,
)
from chatballs.conversations.models import (
    Conversation,
    LifecycleState,
)
from chatballs.conversations.reply_claim import claim_for_reply
from chatballs.conversations.selectors import (
    MESSAGES_NEWER_KEYS,
    MESSAGES_OLDER_KEYS,
    conversation_messages,
)
from chatballs.conversations.serializers import (
    message_payload,
)
from chatballs.conversations.services import (
    ClaimError,
    post_operator_message,
    request_contact,
)
from chatballs.conversations.template_send_guard import (
    UnfilledTemplateVariables,
    require_filled_text,
)
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.conversations.template_updates import add_template_updates
from chatballs.i18n import t

# Окно инбокса и окно истории: размеры продуктовые, клиент может запросить
# меньше, больше — только до потолка api.pagination.
MESSAGE_WINDOW_SIZE = 50


class ConversationMessageView(ConversationViewBase):
    # Читает историю тот, кто видит диалог; пишет — тот, кто его ведёт.
    required_capabilities = {"GET": "conversations.view", "POST": "conversations.operate"}
    required_capability = "conversations.operate"

    def get(self, request: Request, conversation_id: int) -> Response:
        """Окно истории.

        `after` — что появилось после последнего показанного сообщения (этим
        живёт обновление открытого диалога); `before` — что было до самого
        раннего показанного (этим живёт прокрутка вверх). Без курсора — хвост
        переписки, то есть последние сообщения.
        """
        try:
            conversation = self._conversation(request, conversation_id)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        params = request.query_params
        limit = window_size(params, default=MESSAGE_WINDOW_SIZE)
        messages = conversation_messages(conversation)
        after = cursor_id(params, "after")
        if after is not None:
            payload = window_payload(
                window(messages, keys=MESSAGES_NEWER_KEYS, limit=limit, after=after),
                message_payload,
            )
            add_template_updates(payload["items"], organization_id=conversation.organization_id)
            return Response(payload)
        page = window(
            messages,
            keys=MESSAGES_OLDER_KEYS,
            limit=limit,
            after=cursor_id(params, "before"),
        )
        # Курсор считается по окну «от свежих к старым» — это самое раннее
        # сообщение окна, с него продолжится прокрутка вверх. Наружу список
        # уходит в хронологическом порядке, как его рисует лента.
        payload = window_payload(page, message_payload)
        add_template_updates(payload["items"], organization_id=conversation.organization_id)
        payload["items"].reverse()
        return Response(payload)

    def post(self, request: Request, conversation_id: int) -> Response:
        try:
            conversation = self._conversation(request, conversation_id, "conversations.operate")
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        text = str(request.data.get("text", "")).strip()
        if not text:
            return Response({"detail": t("ai.empty_message")}, status=400)
        if conversation.lifecycle != LifecycleState.OPEN:
            return Response({"detail": t("conversations.closed")}, status=409)
        try:
            require_filled_text(text)
        except UnfilledTemplateVariables as error:
            return Response(error.payload(), status=400)
        if request.data.get("suggestionId") is not None:
            from rest_framework import serializers

            from chatballs.ai.assistance_send import send_suggestion

            suggestion_id = serializers.UUIDField().run_validation(request.data["suggestionId"])
            message = send_suggestion(
                context=request.tenant_context, conversation_id=conversation_id,
                suggestion_id=suggestion_id, key=request.data.get("operationKey"), text=text,
            )
            return Response({"message": message_payload(message)}, status=201)
        claimed = claim_for_reply(self, request, conversation)
        if isinstance(claimed, Response):
            return claimed
        conversation = claimed
        try:
            message = post_operator_message(
                context=request.tenant_context, conversation=conversation, text=text,
                operation_id=request.headers.get("Idempotency-Key"),
            )
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        except ClaimError as error:
            return Response({"detail": str(error)}, status=409)
        return Response({"message": message_payload(message)}, status=201)


class ConversationRequestContactView(ConversationViewBase):
    required_capability = "conversations.operate"

    def post(self, request: Request, conversation_id: int) -> Response:
        try:
            conversation = self._conversation(request, conversation_id, "conversations.operate")
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        if not conversation.contact_id or not conversation.connection_id:
            return Response({"detail": t("conversations.no_channel_for_contact")}, status=409)
        if conversation.lifecycle != LifecycleState.OPEN:
            return Response({"detail": t("conversations.closed")}, status=409)
        if conversation.contact.phone:
            return Response({"detail": t("conversations.contact_already_received")}, status=409)
        try:
            message = request_contact(
                context=request.tenant_context,
                conversation=conversation,
                operation_id=request.headers.get("Idempotency-Key"),
            )
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        except ClaimError as error:
            return Response({"detail": str(error)}, status=409)
        self._audit(request, "contact_requested", conversation)
        return Response({"message": message_payload(message)}, status=201)
