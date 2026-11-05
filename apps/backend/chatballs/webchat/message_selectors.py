"""Customer record access shared by widget history, anchors and file links."""

from django.db.models import Q

from chatballs.conversations.history_selectors import customer_visible_messages
from chatballs.conversations.models import Message
from chatballs.native_mirror.visibility import visible_messages
from chatballs.webchat.models import WebSession


def session_messages(session: WebSession):
    # The caller resolves the session and enters its tenant transaction first.
    return visible_messages(customer_visible_messages(Message.objects.filter(
        Q(ai_reply_to__isnull=True) | Q(ai_delivery__sent=True),
        organization_id=session.organization_id,
        conversation__organization_id=session.organization_id,
        conversation__contact_id=session.identity.contact_id,
        conversation__channel_id=session.connection.channel_id,
        conversation__connection_id=session.connection_id,
    )))
