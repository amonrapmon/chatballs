"""Visitor observations are scoped to the visible dialog and exact WebSession."""

from rest_framework.response import Response

from chatballs.conversations.models import Conversation
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.i18n import t
from chatballs.webchat.models import WebSession
from chatballs.webchat.observations import session_observations


class VisitorStateView(ConversationViewBase):
    def get(self, request, conversation_id):
        try:
            conversation = self._conversation(request, conversation_id)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        sessions = WebSession.objects.filter(
            organization_id=conversation.organization_id, connection_id=conversation.connection_id,
            identity__contact_id=conversation.contact_id,
            identity__external_user_id=conversation.external_chat_id,
        ).order_by("pk")
        return Response({"sessions": [session_observations(session) for session in sessions]})
