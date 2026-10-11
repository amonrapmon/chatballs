"""Deliver the completed turn outside its database transaction."""

from chatballs.conversations import transports
from chatballs.integrations.models import IntegrationProvider


def deliver(turn, text: str) -> None:
    if not text or turn.conversation.connection is None:
        return

    # Gateway delivery was durably queued with the AI result commit.
    if turn.conversation.connection.provider == IntegrationProvider.GATEWAY:
        return

    transports.send_reply(
        turn.conversation.connection,
        chat_id=turn.conversation.external_chat_id,
        user_id=turn.user_id,
        text=text,
    )
