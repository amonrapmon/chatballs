"""Visitor observations are scoped to the visible dialog and its contact's WebSessions."""

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
        # Веб-приём не заполняет external_chat_id: виджет находит свой диалог по
        # каналу и контакту сессии, и сотруднику сессии отдаются по той же связи.
        sessions = WebSession.objects.filter(
            organization_id=conversation.organization_id, connection_id=conversation.connection_id,
            identity__contact_id=conversation.contact_id,
        ).order_by("pk")
        return Response({"sessions": [session_observations(session) for session in sessions]})
