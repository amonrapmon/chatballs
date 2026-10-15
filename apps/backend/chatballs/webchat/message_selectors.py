"""Customer record access shared by widget history, anchors and file links."""

from chatballs.conversations.history_selectors import customer_visible_messages
from chatballs.conversations.models import Message
from chatballs.webchat.models import WebSession


def session_messages(session: WebSession):
    # The caller resolves the session and enters its tenant transaction first.
    return customer_visible_messages(Message.objects.filter(
        organization_id=session.organization_id,
        conversation__organization_id=session.organization_id,
        conversation__contact_id=session.identity.contact_id,
        conversation__channel_id=session.connection.channel_id,
        conversation__connection_id=session.connection_id,
    ))
