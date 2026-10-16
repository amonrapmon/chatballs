"""Only invalidations; employee sockets reauthorize before delivery."""

from django.db import transaction

from chatballs.conversations.realtime import conversation_group
from chatballs.realtime import publish


def notify_suggestion(suggestion):
    conversation_id = suggestion.attempt.conversation_id
    payload = {"type": "reply_assistance.changed", "conversationId": conversation_id,
               "attemptId": str(suggestion.attempt.public_id)}
    transaction.on_commit(lambda: publish(conversation_group(conversation_id), payload))
