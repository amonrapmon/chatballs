"""Инструменты в формате OpenAI Chat Completions (SPEC-0023 R-11).

Перевод между своими типами (chatballs.ai.provider.base) и телом запроса и
ответа: `tools` в запросе, `tool_calls` у сообщения assistant, сообщение роли
`tool` с `tool_call_id`. Транспорт остаётся в openai_http.
"""

from __future__ import annotations

import json

from chatballs.ai.provider.base import ChatMessage, ProviderError, ToolCall, ToolSpec
from chatballs.i18n import t

# Схема инструмента без параметров: пустой объект принимают все провайдеры,
# отсутствие `parameters` — не все.
NO_PARAMETERS = {"type": "object", "properties": {}}

# Проверочный инструмент: по ответу на запрос с ним видно, принимает ли endpoint
# `tools` и возвращает ли модель `tool_calls` (SPEC-0023 R-10).
PROBE_TOOL = ToolSpec(name="ping", description="Returns pong.")
PROBE_MESSAGES = [ChatMessage(role="user", content="Call the ping tool.")]
PROBE_PARAMS = {
    "tool_choice": {"type": "function", "function": {"name": PROBE_TOOL.name}},
    "max_tokens": 64,
}


def tools_payload(tools: list[ToolSpec]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters or NO_PARAMETERS,
            },
        }
        for tool in tools
    ]


def message_payload(message: ChatMessage) -> dict:
    if message.role == "tool":
        return {"role": "tool", "tool_call_id": message.tool_call_id, "content": message.content}
    payload: dict = {"role": message.role, "content": message.content}
    if message.tool_calls:
        # У сообщения с вызовами текста обычно нет: пустую строку часть
        # провайдеров отклоняет, null принимают все.
        payload["content"] = message.content or None
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": call.name,
                    "arguments": json.dumps(call.arguments, ensure_ascii=False),
                },
            }
            for call in message.tool_calls
        ]
    return payload


def parse_tool_calls(message: dict) -> tuple[ToolCall, ...]:
    """Вызовы из ответа модели; аргументы приходят строкой JSON.

    Битые аргументы — сбой ответа, а не отказ запроса: повтор его лечит.
    """
    calls = []
    for item in message.get("tool_calls") or []:
        try:
            function = item["function"]
            arguments = json.loads(function.get("arguments") or "{}")
            if not isinstance(arguments, dict):
                raise TypeError("tool arguments are not an object")
            calls.append(ToolCall(id=str(item["id"]), name=str(function["name"]), arguments=arguments))
        except (KeyError, TypeError, ValueError) as error:
            raise ProviderError(t("ai.unexpected_provider_response", error=error)) from error
    return tuple(calls)
