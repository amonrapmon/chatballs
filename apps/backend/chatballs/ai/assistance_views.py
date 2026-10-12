"""Employee-only assistance endpoints; no customer API or new UI."""

from rest_framework import serializers
from rest_framework.response import Response

from chatballs.ai.assistance_access import reply_context
from chatballs.ai.assistance_expiry import expire_attempt
from chatballs.ai.assistance_payload import attempt_payload, suggestion_payload
from chatballs.ai.assistance_services import (
    attempt_for,
    reject_suggestion,
    request_suggestion,
)
from chatballs.ai.models import ReplyAssistanceAttempt
from chatballs.conversations.view_base import ConversationViewBase


class RequestInput(serializers.Serializer):
    operationKey = serializers.CharField(max_length=160)
    attemptId = serializers.UUIDField(required=False)


class AssistanceListView(ConversationViewBase):
    required_capability = "conversations.operate"

    def get(self, request, conversation_id):
        _, conversation = reply_context(request.tenant_context, conversation_id)
        attempts = ReplyAssistanceAttempt.objects.filter(
            organization_id=request.tenant_context.organization_id, conversation=conversation,
        ).order_by("-created_at", "-id")[:20]
        return Response({"items": [attempt_payload(expire_attempt(a)) for a in attempts]})

    def post(self, request, conversation_id):
        data = RequestInput(data=request.data)
        data.is_valid(raise_exception=True)
        suggestion = request_suggestion(
            context=request.tenant_context, conversation_id=conversation_id,
            key=data.validated_data["operationKey"],
            attempt_id=data.validated_data.get("attemptId"),
        )
        return Response({"suggestion": suggestion_payload(suggestion)}, status=202)


class AssistanceDetailView(ConversationViewBase):
    required_capability = "conversations.operate"

    def get(self, request, conversation_id, attempt_id):
        _, conversation = reply_context(request.tenant_context, conversation_id)
        attempt = attempt_for(request.tenant_context, conversation, attempt_id)
        return Response({"attempt": attempt_payload(expire_attempt(attempt))})


class AssistanceRejectView(ConversationViewBase):
    required_capability = "conversations.operate"

    def post(self, request, conversation_id, suggestion_id):
        suggestion = reject_suggestion(
            context=request.tenant_context, conversation_id=conversation_id,
            suggestion_id=suggestion_id,
        )
        return Response({"suggestion": suggestion_payload(suggestion)})
