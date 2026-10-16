"""Finalize an AI turn against current control state, inside tenant_atomic."""

from collections.abc import Callable
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from chatballs.ai.diagnostic_capture import finish_diagnostic, record_planning_failure
from chatballs.ai.runtime import HANDOFF_TOKEN
from chatballs.ai.turn import record_turn
from chatballs.conversations import ai_turn_result, tool_call_events
from chatballs.conversations.models import AiTurnState, Conversation, Message
from chatballs.identity.operation_modes import autonomous_allowed, lock_organization
from chatballs.native_mirror.supersession import current_revision
from chatballs.tenancy.database import tenant_atomic


def _commit_if_current(*, turn, context, persist: Callable[[], str]) -> str | None:
    with tenant_atomic(context):
        if not refresh_turn_control(turn, context):
            return None
        return persist()


def refresh_turn_control(turn, context):
    organization = lock_organization(context.organization_id)
    # The network phase may have outlived a human takeover. Use the same lock
    # and fresh row for the check and for store_answer's subsequent updates.
    turn.conversation = Conversation.objects.select_for_update(of=("self",)).select_related(
        "contact", "connection", "channel__ai_agent",
    ).get(pk=turn.conversation.pk, organization_id=context.organization_id)
    turn.message = Message.objects.select_for_update().get(
        pk=turn.message.pk, organization_id=context.organization_id,
        conversation_id=turn.conversation.pk,
    )
    if (not autonomous_allowed(turn.conversation.channel, organization=organization,
                               connection=turn.conversation.connection, conversation=turn.conversation)
            or turn.mode_version != organization.operation_mode_version
            or (turn.mirror_revision is not None
                and current_revision(conversation_id=turn.conversation.pk) != turn.mirror_revision)
            or turn.message.ai_turn_state != AiTurnState.RUNNING):
        if turn.message.ai_turn_state == AiTurnState.RUNNING:
            turn.message.ai_turn_state = AiTurnState.DONE
            turn.message.save(update_fields=["ai_turn_state"])
        return False
    return True


def store_failure_if_current(*, turn, context, error):
    if not refresh_turn_control(turn, context):
        return None
    return ai_turn_result.store_failure(turn=turn, context=context, error=error)


def finish_planning_failure(*, turn, context, error):
    if not refresh_turn_control(turn, context):
        return None
    record_planning_failure(
        turn.message, turn.agent, turn.conversation, turn.pseudonymizer, error
    )
    return ai_turn_result.store_failure(turn=turn, context=context, error=error)


def finish_requested_turn(turn, context, plan, answer):
    if not refresh_turn_control(turn, context):
        return None
    finish_diagnostic(turn.message, plan, answer)
    reply = record_turn(agent=turn.agent, plan=plan, answer=answer)
    tool_call_events.record_tool_calls(turn.message, answer.tool_calls)
    deadline = turn.message.created_at + timedelta(seconds=settings.CHATBALLS_AI_TURN_DEADLINE_SECONDS)
    error = answer.error
    if timezone.now() >= deadline:
        error = "turn deadline passed"
    if error is not None:
        return ai_turn_result.store_failure(turn=turn, context=context, error=error)
    return ai_turn_result.store_answer(turn=turn, context=context, text=reply,
                                      prepared=answer.prepared_reply,
                                      handoff=bool(answer.result and HANDOFF_TOKEN in answer.result.text))
