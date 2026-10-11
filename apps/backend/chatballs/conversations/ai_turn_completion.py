"""Commit an AI result only while its inbound turn still owns the dialog.

The decision, history, notifications, resulting Message and Gateway outbox
are in one tenant transaction. Losing workers have no completion side effects.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from chatballs.ai.diagnostic_capture import (
    finish_diagnostic,
    record_planning_failure,
    start_diagnostic,
)
from chatballs.ai.turn import record_turn
from chatballs.conversations import ai_turn_result, tool_call_events
from chatballs.conversations.ai_turn_guard import lock_eligible_turn
from chatballs.conversations.models import AiTurnState
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic

if TYPE_CHECKING:
    from chatballs.ai.turn import TurnAnswer, TurnPlan
    from chatballs.conversations.ai_turn import Turn


def _commit_if_current(
    *, turn: Turn, context: TenantContext, persist: Callable[[], str]
) -> str | None:
    """None means rejected (including duplicate); empty string may be valid."""
    with tenant_atomic(context):
        locked = lock_eligible_turn(
            message_id=turn.message.id,
            context=context,
            accepted_states=(AiTurnState.RUNNING,),
            agent_id=turn.agent.id,
        )
        if locked is None:
            return None
        turn.message, turn.conversation, _ = locked
        return persist()


def finish_planning_failure(
    *, turn: Turn, context: TenantContext, error: Exception
) -> str | None:
    def persist() -> str:
        record_planning_failure(
            turn.message, turn.agent, turn.conversation, turn.pseudonymizer, error
        )
        return ai_turn_result.store_failure(turn=turn, context=context, error=error)

    return _commit_if_current(turn=turn, context=context, persist=persist)


def finish_answer(
    *, turn: Turn, context: TenantContext, plan: TurnPlan, answer: TurnAnswer
) -> str | None:
    def persist() -> str:
        # Even the optional diagnostic snapshot belongs to the winning result:
        # a stale worker must not overwrite the winning worker's trace.
        start_diagnostic(turn.message, plan)
        finish_diagnostic(turn.message, plan, answer)
        reply = record_turn(agent=turn.agent, plan=plan, answer=answer)
        tool_call_events.record_tool_calls(turn.message, answer.tool_calls)
        if answer.error is not None:
            return ai_turn_result.store_failure(
                turn=turn, context=context, error=answer.error
            )
        return ai_turn_result.store_answer(turn=turn, context=context, text=reply)

    return _commit_if_current(turn=turn, context=context, persist=persist)
