"""Deliver the completed turn outside its database transaction."""

from chatballs.conversations.ai_reply_delivery import deliver_saved


def deliver(turn, text: str, context) -> None:
    deliver_saved(turn.message.pk, context)
