"""Quality management grants never follow ordinary operator visibility."""

from rest_framework.exceptions import NotFound

from chatballs.conversations.management_scope import management_scope
from chatballs.i18n import t


def quality_scope(context):
    return management_scope(context, forbidden_key="quality.forbidden").conversations()


def require_quality_conversation(context, conversation_id):
    conversation = quality_scope(context).filter(pk=conversation_id).first()
    if conversation is None:
        raise NotFound(t("quality.not_found"))
    return conversation
