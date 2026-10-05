"""Вызов инструмента агентом в ленте диалога (SPEC-0023 R-19).

Каждый вызов — системное событие с кодом: название инструмента, итог, код
ошибки, длительность и ход, к которому вызов относится. Аргументов и ответа
инструмента здесь нет и быть не может: в след вызова (``ToolCallRecord``) они
не попадают. Фразу по этим параметрам собирает бэкенд на языке читателя.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from chatballs.conversations.models import Message, MessageAuthor, SystemEvent
from chatballs.i18n import t

if TYPE_CHECKING:  # pragma: no cover - только для подсказок типов
    from chatballs.ai.tool_calls import ToolCallRecord

RESULT_OK = "ok"
RESULT_ERROR = "error"

# Коды, для которых в каталоге есть текст; остальным достаётся общий.
_ERROR_CODES = frozenset(
    {
        "timeout",
        "unreachable",
        "unauthorized",
        "address_forbidden",
        "bad_response",
        "rejected",
        "not_found",
        "invalid_arguments",
        "unknown_tool",
        "tool_error",
    }
)


def record_tool_calls(turn_message: Message, calls: Iterable[ToolCallRecord]) -> None:
    """Шаг в транзакции: вызовы хода — событиями в ленту, по порядку.

    Признак хода — входящее сообщение, по которому он шёл: по нему лента
    собирает вызовы одного хода вместе. Текст события пуст: в историю для
    модели и в виджет клиента оно не попадает.
    """
    for call in calls:
        Message.objects.create(
            conversation=turn_message.conversation,
            author_type=MessageAuthor.SYSTEM,
            system_event=SystemEvent.TOOL_CALLED,
            system_params={
                "tool": call.title,
                "result": RESULT_ERROR if call.error else RESULT_OK,
                "error": call.error,
                "durationMs": call.duration_ms,
                "turnId": turn_message.id,
            },
        )


def _error_text(code: str) -> str:
    return t(f"conversations.tool_error.{code if code in _ERROR_CODES else 'unknown'}")


def _duration_text(duration_ms: int) -> str:
    seconds = f"{duration_ms / 1000:.1f}".replace(".", t("format.decimal_separator"))
    return t("conversations.tool_duration", seconds=seconds)


def tool_call_text(params: dict) -> str:
    """Фраза события на языке читателя."""
    tool = params.get("tool", "")
    if params.get("error"):
        return t(
            "conversations.system.tool_called_failed",
            tool=tool,
            error=_error_text(str(params["error"])),
        )
    return t(
        "conversations.system.tool_called",
        tool=tool,
        duration=_duration_text(int(params.get("durationMs") or 0)),
    )


def tool_call_payload(params: dict) -> dict[str, object]:
    """Параметры события для ленты: по ним вызовы одного хода собираются вместе."""
    code = str(params.get("error") or "")
    return {
        "tool": params.get("tool", ""),
        "ok": not code,
        "errorCode": code,
        "error": _error_text(code) if code else "",
        "durationMs": int(params.get("durationMs") or 0),
        "turnId": params.get("turnId"),
    }
