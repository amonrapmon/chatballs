"""Обработчики outbox-событий домена диалогов."""

from chatballs.ai.assistance_generation import run_requested_assistance
from chatballs.ai.assistance_services import ASSISTANCE_REQUESTED
from chatballs.conversations.ai_turn import AI_TURN_REQUESTED, run_requested_turn
from chatballs.conversations.email_continuation import EMAIL_SEND_REQUESTED
from chatballs.conversations.email_delivery import deliver_email_reply
from chatballs.conversations.participant_notifications import (
    deliver_specialist_notice,  # noqa: F401
)
from chatballs.conversations.rules.executor import run_due_execution
from chatballs.conversations.rules.scheduler import RULE_EXECUTION_DUE
from chatballs.events.handlers import register
from chatballs.tenancy.context import TenantContext


@register(ASSISTANCE_REQUESTED, manages_own_transaction=True)
def handle_reply_assistance(payload: dict, context: TenantContext | None) -> None:
    if context is not None:
        run_requested_assistance(payload, context)


@register(AI_TURN_REQUESTED, manages_own_transaction=True)
def handle_ai_turn_requested(payload: dict, context: TenantContext | None) -> None:
    """Ход AI сам управляет транзакциями: он ходит к провайдеру и в мессенджер,
    и держать ради этого одну транзакцию на весь обработчик нельзя."""
    if context is None:  # pragma: no cover - событие диалога всегда арендное
        return
    run_requested_turn(payload, context)


@register(EMAIL_SEND_REQUESTED, manages_own_transaction=True)
def handle_email_send_requested(payload: dict, context: TenantContext | None) -> None:
    if context is not None:
        deliver_email_reply(payload, context)


@register(RULE_EXECUTION_DUE, manages_own_transaction=True)
def handle_rule_execution_due(payload: dict, context: TenantContext | None) -> None:
    if context is not None:
        run_due_execution(payload, context)
