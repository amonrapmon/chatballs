from rest_framework.request import Request
from rest_framework.response import Response

from chatballs.conversations.models import (
    Conversation,
)
from chatballs.conversations.serializers import (
    conversation_payload,
)
from chatballs.conversations.services import (
    ClaimError,
    claim_conversation,
    close_conversation,
    mark_conversation_as_spam,
    release_to_ai,
    return_to_queue,
)
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.i18n import t


class ConversationClaimView(ConversationViewBase):
    required_capability = "conversations.operate"

    def post(self, request: Request, conversation_id: int) -> Response:
        try:
            self._conversation(request, conversation_id, self.required_capability)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        try:
            conversation = claim_conversation(
                context=request.tenant_context, conversation_id=conversation_id,
                operation_id=request.headers.get("Idempotency-Key"),
            )
        except ClaimError as error:
            return Response({"detail": str(error)}, status=409)
        self._audit(request, "claimed", conversation)
        return Response(
            {
                "conversation": conversation_payload(
                    conversation,
                    detailed=True,
                    viewer_id=request.user.id,
                )
            }
        )


class ConversationReleaseView(ConversationViewBase):
    required_capability = "conversations.operate"

    def post(self, request: Request, conversation_id: int) -> Response:
        try:
            self._conversation(request, conversation_id, self.required_capability)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        try:
            conversation = release_to_ai(
                context=request.tenant_context, conversation_id=conversation_id,
                operation_id=request.headers.get("Idempotency-Key"),
            )
        except ClaimError as error:
            return Response({"detail": str(error)}, status=409)
        self._audit(request, "released_to_ai", conversation)
        return Response(
            {
                "conversation": conversation_payload(
                    conversation,
                    detailed=True,
                    viewer_id=request.user.id,
                )
            }
        )


class ConversationReturnQueueView(ConversationViewBase):
    required_capability = "conversations.operate"

    def post(self, request: Request, conversation_id: int) -> Response:
        try:
            self._conversation(request, conversation_id, self.required_capability)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        try:
            conversation = return_to_queue(
                context=request.tenant_context, conversation_id=conversation_id,
                operation_id=request.headers.get("Idempotency-Key"),
            )
        except ClaimError as error:
            return Response({"detail": str(error)}, status=409)
        self._audit(request, "returned_to_queue", conversation)
        return Response(
            {
                "conversation": conversation_payload(
                    conversation,
                    detailed=True,
                    viewer_id=request.user.id,
                )
            }
        )
class ConversationCloseView(ConversationViewBase):
    required_capability = "conversations.operate"

    def post(self, request: Request, conversation_id: int) -> Response:
        try:
            self._conversation(request, conversation_id, self.required_capability)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        try:
            conversation = close_conversation(
                context=request.tenant_context, conversation_id=conversation_id,
                operation_id=request.headers.get("Idempotency-Key"),
            )
        except ClaimError as error:
            return Response({"detail": str(error)}, status=409)
        self._audit(request, "closed", conversation)
        return Response(
            {
                "conversation": conversation_payload(
                    conversation,
                    detailed=True,
                    viewer_id=request.user.id,
                )
            }
        )


class ConversationSpamView(ConversationViewBase):
    required_capability = "conversations.operate"

    def post(self, request: Request, conversation_id: int) -> Response:
        try:
            self._conversation(request, conversation_id, self.required_capability)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        try:
            conversation = mark_conversation_as_spam(
                context=request.tenant_context, conversation_id=conversation_id,
                operation_id=request.headers.get("Idempotency-Key"),
            )
        except ClaimError as error:
            return Response({"detail": str(error)}, status=409)
        self._audit(request, "marked_spam", conversation)
        return Response(
            {
                "conversation": conversation_payload(
                    conversation,
                    detailed=True,
                    viewer_id=request.user.id,
                )
            }
        )
