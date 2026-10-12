from django.db import transaction
from rest_framework.request import Request
from rest_framework.response import Response

from chatballs.conversations.message_views import (
    ConversationMessageView as ConversationMessageView,
)
from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    LifecycleState,
)
from chatballs.conversations.read_views import (
    ConversationDetailView as ConversationDetailView,
)
from chatballs.conversations.read_views import (
    ConversationListView as ConversationListView,
)
from chatballs.conversations.serializers import (
    conversation_payload,
    message_payload,
)
from chatballs.conversations.services import (
    ClaimError,
    assign_operator,
    claim_conversation,
    close_conversation,
    mark_conversation_as_spam,
    release_to_ai,
    request_contact,
    return_to_queue,
)
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.i18n import t
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import OrganizationMembership
from chatballs.identity.policy import ResourceScope, authorize


class ConversationClaimView(ConversationViewBase):
    required_capability = "conversations.operate"

    def post(self, request: Request, conversation_id: int) -> Response:
        try:
            self._conversation(request, conversation_id, self.required_capability)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        try:
            conversation = claim_conversation(
                context=request.tenant_context, conversation_id=conversation_id
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
                context=request.tenant_context, conversation_id=conversation_id
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
                context=request.tenant_context, conversation_id=conversation_id
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


def claim_for_reply(view: ConversationViewBase, request: Request, conversation: Conversation) -> Conversation | Response:
    """Одно действие взятия (дизайн-базлайн v2, решение 2; ADR-CHATBALLS-0003): первая
    реплика сотрудника (текст или файл) атомарно перехватывает диалог у
    AI/очереди. Возвращает диалог или готовый ответ с ошибкой."""
    if conversation.control_mode != ControlMode.HUMAN:
        try:
            with transaction.atomic():
                conversation = claim_conversation(
                    context=request.tenant_context, conversation_id=conversation.id
                )
        except ClaimError as error:
            return Response({"detail": str(error)}, status=409)
        view._audit(request, "claimed", conversation)
    manager_override = authorize(
        request.tenant_context.membership,
        view.required_capability,
        ResourceScope(conversation.organization_id),
    )
    if conversation.assigned_operator_id != request.user.id and not manager_override:
        return Response({"detail": t("conversations.handled_by_other")}, status=409)
    return conversation




class ConversationRequestContactView(ConversationViewBase):
    required_capability = "conversations.operate"

    def post(self, request: Request, conversation_id: int) -> Response:
        try:
            conversation = self._conversation(request, conversation_id, self.required_capability)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        if not conversation.contact_id or not conversation.connection_id:
            return Response({"detail": t("conversations.no_channel_for_contact")}, status=409)
        if conversation.lifecycle != LifecycleState.OPEN:
            return Response({"detail": t("conversations.closed")}, status=409)
        if conversation.contact.phone:
            return Response({"detail": t("conversations.contact_already_received")}, status=409)
        try:
            message = request_contact(
                context=request.tenant_context,
                conversation=conversation,
            )
        except ClaimError as error:
            return Response({"detail": str(error)}, status=409)
        self._audit(request, "contact_requested", conversation)
        return Response({"message": message_payload(message)}, status=201)


class ConversationCloseView(ConversationViewBase):
    required_capability = "conversations.operate"

    def post(self, request: Request, conversation_id: int) -> Response:
        try:
            self._conversation(request, conversation_id, self.required_capability)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        try:
            conversation = close_conversation(
                context=request.tenant_context, conversation_id=conversation_id
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
                context=request.tenant_context, conversation_id=conversation_id
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


class ConversationGroupView(ConversationViewBase):
    """Перенос диалога в группу и снятие группы (ADR-CHATBALLS-0043 §3)."""

    required_capability = "conversations.operate"

    def post(self, request: Request, conversation_id: int) -> Response:
        try:
            conversation = self._conversation(request, conversation_id, self.required_capability)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        group_id = request.data.get("groupId")
        group = None
        if group_id is not None:
            group = EmployeeGroup.objects.filter(
                organization_id=conversation.organization_id, id=group_id
            ).first()
            if group is None:
                return Response({"detail": t("admin.group_not_found")}, status=400)
        conversation.group = group
        conversation.save(update_fields=["group"])
        self._audit(request, "group_changed", conversation)
        return Response(
            {
                "conversation": conversation_payload(
                    conversation, viewer_id=request.user.id
                )
            }
        )


class ConversationAssigneeView(ConversationViewBase):
    """Назначение и переназначение ответственного (ADR-CHATBALLS-0043 §3)."""

    required_capability = "conversations.operate"

    def post(self, request: Request, conversation_id: int) -> Response:
        try:
            conversation = self._conversation(request, conversation_id, self.required_capability)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        user_id = request.data.get("userId")
        assignee = None
        if user_id is not None:
            membership = (
                OrganizationMembership.objects.select_related("user")
                .filter(
                    organization_id=conversation.organization_id,
                    user_id=user_id,
                    blocked_at__isnull=True,
                )
                .first()
            )
            if membership is None:
                return Response({"detail": t("admin.employee_not_found")}, status=400)
            assignee = membership.user
        conversation = assign_operator(
            context=request.tenant_context,
            conversation_id=conversation.id,
            assignee=assignee,
        )
        self._audit(request, "assignee_changed", conversation)
        return Response(
            {
                "conversation": conversation_payload(
                    conversation, viewer_id=request.user.id
                )
            }
        )
