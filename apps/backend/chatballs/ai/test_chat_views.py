"""Проверочный чат использует шаги живого хода; клиентские данные не записывает."""

import time

from django.conf import settings
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.ai.provider.base import ProviderError
from chatballs.ai.test_chat_data import parse_test_client_data
from chatballs.ai.turn import (
    plan_chat,
    plan_query_embedding,
    record_turn,
    run_query_embedding,
    run_turn_chat,
)
from chatballs.api.permissions import HasCapability
from chatballs.channels.models import Channel
from chatballs.channels.selectors import channel_for_context
from chatballs.conversations.tool_call_events import tool_call_payload
from chatballs.i18n import t
from chatballs.tenancy.database import tenant_atomic


class AgentCardTestChatView(APIView):
    permission_classes = [HasCapability]
    required_capability = "ai.manage"
    tenant_manages_own_transaction = True

    def post(self, request: Request, agent_id: int) -> Response:
        started = time.monotonic()
        calls = []
        body = request.data if isinstance(request.data, dict) else {}
        message = body.get("message", "")
        if not isinstance(message, str) or not message.strip():
            return Response({"detail": t("ai.empty_message")}, status=400)
        history = body.get("history", [])
        if not isinstance(history, list) or any(
            not isinstance(item, dict)
            or item.get("role") not in {"user", "assistant"}
            or not isinstance(item.get("content"), str)
            for item in history
        ):
            return Response({"detail": t("ai.history_must_be_list")}, status=400)
        try:
            with tenant_atomic(request.tenant_context):
                try:
                    channel = channel_for_context(
                        context=request.tenant_context, channel_id=agent_id, capability="ai.view",
                    )
                except Channel.DoesNotExist:
                    return Response({"detail": t("ai.agent_not_found")}, status=404)
                agent = getattr(channel, "ai_agent", None)
                if agent is None or not agent.is_active:
                    raise ProviderError(t("channels.no_active_agent"))
                data = parse_test_client_data(channel, body.get("clientData"))
                history = history[-agent.history_limit:] if agent.history_limit else []
                embedding_job = plan_query_embedding(
                    agent=agent, query=message.strip(), pseudonymizer=data.pseudonymizer,
                )
            embedding = run_query_embedding(embedding_job)
            with tenant_atomic(request.tenant_context):
                plan = plan_chat(
                    agent=agent, message=message.strip(), history=history, embedding=embedding,
                    pseudonymizer=data.pseudonymizer, client=data.client, client_context=data.context_fields,
                )
            answer = run_turn_chat(
                plan, time_left=settings.CHATBALLS_AI_TURN_TIMEOUT - (time.monotonic() - started),
            )
            with tenant_atomic(request.tenant_context):
                reply = record_turn(agent=agent, plan=plan, answer=answer)
            calls = [
                {"name": call.name, **tool_call_payload({
                    "tool": call.title, "error": call.error, "durationMs": call.duration_ms,
                })}
                for call in answer.tool_calls
            ]
            if answer.error is not None:
                raise answer.error
        except ProviderError as error:
            return Response({"detail": t("ai.provider_error", error=error), "toolCalls": calls}, status=502)
        result = answer.result
        return Response({
            "reply": reply,
            "model": result.model,
            "promptTokens": sum(item.result.prompt_tokens for item in answer.rounds if item.result) if answer.rounds else result.prompt_tokens,
            "completionTokens": sum(item.result.completion_tokens for item in answer.rounds if item.result) if answer.rounds else result.completion_tokens,
            "toolCalls": calls,
        })
