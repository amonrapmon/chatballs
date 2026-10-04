"""Имитация вызова инструментов демо-провайдером (SPEC-0023 R-14).

Цикл «модель → вызовы → результаты → модель» должен проверяться без сети и
ключей, поэтому правила здесь механические и одинаковые от запуска к запуску:

- инструмент вызывается, если слова его имени или описания есть в вопросе;
- обязательные параметры заполняются из вопроса: токен с именем параметра,
  иначе число из текста, иначе сам вопрос;
- когда результаты пришли, ответ — их текст.
"""

from __future__ import annotations

import re

from chatballs.ai.provider.base import ChatMessage, ToolCall, ToolSpec
from chatballs.ai.provider.demo import _language_of, _tokens

# Ответ клиенту по результатам: сырой ответ инструмента бывает длинным.
REPLY_LIMIT = 600
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _question(messages: list[ChatMessage]) -> str:
    return next((m.content for m in reversed(messages) if m.role == "user"), "")


def reply_from_results(messages: list[ChatMessage]) -> str | None:
    """Текст результатов, пришедших после последнего вопроса; None — их нет."""
    results: list[str] = []
    for message in reversed(messages):
        if message.role == "user":
            break
        if message.role == "tool":
            results.append(message.content.strip())
    if not results:
        return None
    return "\n".join(reversed(results))[:REPLY_LIMIT]


def _argument(name: str, schema: dict, question: str) -> object | None:
    """Значение обязательного параметра; None — взять его из вопроса неоткуда."""
    kind = schema.get("type", "string")
    if kind == "boolean":
        return False
    number = _NUMBER.search(question)
    if kind in ("number", "integer"):
        if number is None:
            return None
        value = float(number.group().replace(",", "."))
        return int(value) if kind == "integer" or value.is_integer() else value
    # Токен псевдонимизации с именем параметра раскроет сервер (R-12).
    token = f"[[{name}]]"
    if token in question:
        return token
    return number.group() if number else question.strip()


def _arguments(tool: ToolSpec, question: str) -> dict | None:
    properties = tool.parameters.get("properties") or {}
    arguments: dict = {}
    for name in tool.parameters.get("required") or []:
        value = _argument(name, properties.get(name) or {}, question)
        if value is None:
            return None
        arguments[name] = value
    return arguments


def plan_calls(messages: list[ChatMessage], tools: list[ToolSpec]) -> tuple[ToolCall, ...]:
    """Вызовы инструментов, подходящих к последнему вопросу, в порядке списка."""
    question = _question(messages)
    language = _language_of(question)
    query = _tokens(question, language)
    # Номер раунда делает идентификаторы вызовов разными в пределах хода.
    round_number = sum(1 for message in messages if message.tool_calls)
    calls: list[ToolCall] = []
    for tool in tools:
        described = _tokens(f"{tool.name.replace('_', ' ')} {tool.description}", language)
        if not query & described:
            continue
        arguments = _arguments(tool, question)
        if arguments is None:
            continue
        calls.append(
            ToolCall(id=f"demo-{round_number}-{len(calls)}", name=tool.name, arguments=arguments)
        )
    return tuple(calls)
