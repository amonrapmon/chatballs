"""Central audience selection for an already authorized conversation.

Callers resolve conversation access first. Apply limits and cursor conditions
only to the returned queryset: public and internal anchors live in separate
tables, even when their integer ids happen to match.
"""

from chatballs.conversations.audience import ConversationAudience
from chatballs.conversations.comment_models import ConversationComment
from chatballs.conversations.models import Message
from chatballs.conversations.system_events import OPERATOR_ONLY_EVENTS
from chatballs.i18n import t


def conversation_records(conversation, *, audience):
    if audience == ConversationAudience.PUBLIC:
        model, author_field = Message, "author_user"
    elif audience == ConversationAudience.INTERNAL:
        model, author_field = ConversationComment, "author"
    else:
        raise ValueError(t("comments.audience_invalid"))
    records = model.objects.filter(
        organization_id=conversation.organization_id, conversation_id=conversation.pk
    )
    if audience == ConversationAudience.INTERNAL:
        records = records.filter(audience=ConversationAudience.INTERNAL)
    return records.select_related(author_field)


def customer_visible_messages(records):
    """Restrict an authorized Message queryset before cursors or AI limits.

    Comments live in a separate table. Operator-only Message events must also
    stay out of customer history, direct file access and model context.
    """
    if records.model is not Message:
        raise ValueError(t("comments.audience_invalid"))
    return records.exclude(system_event__in=OPERATOR_ONLY_EVENTS)
