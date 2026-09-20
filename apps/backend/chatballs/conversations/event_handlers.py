"""Обработчики outbox-событий домена диалогов."""

from chatballs.conversations.ai_turn import AI_TURN_REQUESTED, run_requested_turn
from chatballs.events.handlers import register
from chatballs.tenancy.context import TenantContext


@register(AI_TURN_REQUESTED, manages_own_transaction=True)
def handle_ai_turn_requested(payload: dict, context: TenantContext | None) -> None:
    """Ход AI сам управляет транзакциями: он ходит к провайдеру и в мессенджер,
    и держать ради этого одну транзакцию на весь обработчик нельзя."""
    if context is None:  # pragma: no cover - событие диалога всегда арендное
        return
    run_requested_turn(payload, context)
