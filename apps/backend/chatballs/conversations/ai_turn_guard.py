"""Atomic eligibility check for AI-turn work, shared by every completion path.

Call inside tenant_atomic(). Lock order is always Conversation -> inbound
Message, matching operator reply paths. Never hold these locks during LLM,
transcription or external provider calls.
"""

from __future__ import annotations

from collections.abc import Iterable

from chatballs.native_mirror.supersession import current_revision
from chatballs.conversations.models import (
    AiTurnState,
    ControlMode,
    Conversation,
    LifecycleState,
    Message,
)
from chatballs.tenancy.context import TenantContext


def lock_eligible_turn(
    *,
    message_id: int,
    context: TenantContext,
    accepted_states: Iterable[str],
    agent_id: int | None = None,
    expected_revision: int | None = None,
):
    """Return the locked (Message, Conversation, AIAgent), or reject stale work.

    The first read discovers only the conversation ID. It is never an
    authorization or freshness check. The two locked rows are re-read after
    acquiring the conversation lock, so a takeover and this commit serialize.
    """
    conversation_id = (
        Message.objects.filter(id=message_id).values_list("conversation_id", flat=True).first()
    )
    if conversation_id is None:
        return None

    conversation = (
        Conversation.objects.select_for_update(of=("self",))
        .select_related("channel__ai_agent", "channel__organization", "contact", "connection")
        .filter(id=conversation_id, organization_id=context.organization_id)
        .first()
    )
    if conversation is None:
        return None
    # Read the epoch before locking Message. The conversation lock makes
    # it stable: every trusted mirror event must acquire that same lock.
    actual_revision = (
        current_revision(conversation_id=conversation.id)
        if expected_revision is not None else None
    )
    message = (
        Message.objects.select_for_update(of=("self",))
        .filter(id=message_id, conversation_id=conversation.id)
        .first()
    )
    if message is None or message.ai_turn_state not in accepted_states:
        return None

    agent = getattr(conversation.channel, "ai_agent", None)
    if (
        conversation.lifecycle != LifecycleState.OPEN
        or conversation.control_mode != ControlMode.AI
        or agent is None
        or not agent.is_active
        or (agent_id is not None and agent.id != agent_id)
        or (expected_revision is not None and actual_revision != expected_revision)
    ):
        # The current worker has lost eligibility. A pending/running turn must
        # not leave the UI permanently showing "typing".
        message.ai_turn_state = AiTurnState.DONE
        message.save(update_fields=["ai_turn_state"])
        return None

    return message, conversation, agent
