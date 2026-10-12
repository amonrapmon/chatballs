import hashlib
import json

from chatballs.conversations.models import MessageAuthor


def public_history_snapshot(conversation, completed_at):
    """Explicit allowlist; internal metadata and system events never enter AI input.

    Internal comments are not implemented in this checkout. Their later
    integration must preserve this allowlist and add the public visibility filter.
    """
    messages = conversation.messages.filter(
        organization_id=conversation.organization_id, created_at__lte=completed_at,
        author_type__in=(MessageAuthor.CONTACT, MessageAuthor.OPERATOR, MessageAuthor.AI),
        system_event="",
    ).order_by("created_at", "id")
    snapshot = [
        {"id": message.pk, "author_type": message.author_type,
         "author_user_id": message.author_user_id, "created_at": message.created_at.isoformat(),
         "kind": message.kind, "text": message.text, "content_html": message.content_html,
         "transcript": message.transcript, "duration_seconds": message.duration_seconds,
         "attachment_name": message.attachment_name, "attachment_content_type": message.attachment_content_type}
        for message in messages
    ]
    revision = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return snapshot, revision
