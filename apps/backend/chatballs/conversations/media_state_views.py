"""Authenticated in-place media status read for already visible native Messages."""
from rest_framework.request import Request
from rest_framework.response import Response

from chatballs.conversations.models import Conversation, Message
from chatballs.conversations.serializers import message_payload
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.conversations.voice_views import _visible_message


class MessageMediaStateView(ConversationViewBase):
    required_capability = "conversations.view"

    def get(self, request: Request, message_id: int) -> Response:
        try:
            message = _visible_message(request, message_id)
        except (Message.DoesNotExist, Conversation.DoesNotExist):
            return Response({"error": "not_found"}, status=404)
        if not message.connector_media:
            return Response({"error": "not_found"}, status=404)
        result = Response({"message": message_payload(message)})
        result["Cache-Control"] = "private, no-store"
        return result
