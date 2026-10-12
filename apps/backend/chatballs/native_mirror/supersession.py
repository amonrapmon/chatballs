"""AI-turn epoch checks shared by the native mirror and AI orchestrator.

The Conversation row is the serialization point for both scheduling and
supersession. Callers MUST already be inside a tenant transaction and hold a
select_for_update lock on that Conversation. Never call LLMs here.
"""

from __future__ import annotations

from chatballs.conversations.models import AiTurnState, Message
from chatballs.native_mirror.models import NativeMirrorConversationState


def current_revision(*, conversation_id: int) -> int:
    """Revision observed while holding the conversation's row lock.

    The mirror state is optional until the first native reply. Zero is the
    initial epoch; no per-turn table or migration is required.
    """
    revision = (
        NativeMirrorConversationState.objects.filter(conversation_id=conversation_id)
        .values_list("revision", flat=True)
        .first()
    )
    return revision if revision is not None else 0


def supersede_active_turns(*, conversation_id: int) -> int:
    """Terminalize old AI work after an authorized mirror Message is stored.

    This must execute in the same transaction as the mirror Message and its
    revision increment, with the Conversation locked first. The subsequent
    AI completion sees DONE or a different revision, and writes nothing.
    """
    return Message.objects.filter(
        conversation_id=conversation_id,
        ai_turn_state__in=(AiTurnState.PENDING, AiTurnState.RUNNING),
    ).update(ai_turn_state=AiTurnState.DONE)
