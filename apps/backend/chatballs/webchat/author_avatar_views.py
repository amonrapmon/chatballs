"""Session-scoped delivery of a public message author's photo."""

from django.http import FileResponse
from rest_framework.response import Response

from chatballs.i18n import t
from chatballs.webchat.access import _PublicSession, _resolved_web_session
from chatballs.webchat.author_avatars import operator_author, with_operator_authors
from chatballs.webchat.message_selectors import session_messages


class WebchatAuthorAvatarView(_PublicSession):
    def get(self, request, message_id):
        with _resolved_web_session(request) as (_context, session):
            if session is None:
                return Response({"detail": t("webchat.session_not_found")}, status=401)
            message = with_operator_authors(session_messages(session), session).filter(id=message_id).first()
            author = operator_author(message) if message else None
            if author is None or not author.avatar:
                return Response({"detail": t("conversations.message_not_found")}, status=404)
            try:
                response = FileResponse(author.avatar.open("rb"), content_type=author.avatar_content_type or "image/jpeg")
            except FileNotFoundError:
                return Response({"detail": t("conversations.message_not_found")}, status=404)
            response["Cache-Control"] = "private, no-store"
            response["X-Content-Type-Options"] = "nosniff"
            return response
