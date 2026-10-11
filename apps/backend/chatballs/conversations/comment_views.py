"""Protected, separately paginated internal history. No edit/delete surface."""

from collections.abc import Mapping

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from chatballs.api.pagination import cursor_id, window, window_payload, window_size
from chatballs.conversations.audience import ConversationAudience
from chatballs.conversations.comment_access import comment_conversation
from chatballs.conversations.comment_services import create_comment
from chatballs.conversations.history_selectors import conversation_records
from chatballs.conversations.selectors import MESSAGES_NEWER_KEYS, MESSAGES_OLDER_KEYS
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.i18n import t
from chatballs.identity.avatars import user_avatar_url_in
from chatballs.tenancy.database import tenant_atomic


def comment_payload(comment):
    return {
        "id": comment.pk,
        "conversationId": comment.conversation_id,
        "audience": comment.audience,
        "text": comment.text,
        "author": {
            "id": comment.author_id,
            "name": comment.author.full_name or comment.author.email,
            "avatarUrl": user_avatar_url_in(comment.author, comment.organization_id),
        },
        "createdAt": comment.created_at.isoformat(),
        "operationId": str(comment.operation_id),
    }


class ConversationCommentsView(ConversationViewBase):
    required_capabilities = {"GET": "conversations.view", "POST": "conversations.operate"}

    def get(self, request, conversation_id):
        with tenant_atomic(request.tenant_context):
            conversation = comment_conversation(
                context=request.tenant_context, conversation_id=conversation_id,
            )
            records = conversation_records(conversation, audience=ConversationAudience.INTERNAL)
            params = request.query_params
            after = cursor_id(params, "after")
            page = window(
                records, keys=MESSAGES_NEWER_KEYS if after is not None else MESSAGES_OLDER_KEYS,
                limit=window_size(params),
                after=after if after is not None else cursor_id(params, "before"),
            )
            payload = window_payload(page, comment_payload)
            if after is None:
                payload["items"].reverse()
            return Response(payload)

    def post(self, request, conversation_id):
        if not isinstance(request.data, Mapping):
            raise ValidationError(t("comments.body_invalid"))
        comment, created = create_comment(
            context=request.tenant_context, conversation_id=conversation_id,
            audience=request.data.get("audience"), text=request.data.get("text"),
            operation_id=request.data.get("operationId"),
        )
        return Response({"comment": comment_payload(comment)}, status=201 if created else 200)
