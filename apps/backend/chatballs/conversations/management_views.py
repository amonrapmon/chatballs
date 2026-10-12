from rest_framework.request import Request
from rest_framework.response import Response

from chatballs.conversations.assignment import assign_operator, move_conversation
from chatballs.conversations.models import Conversation
from chatballs.conversations.serializers import conversation_payload
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.i18n import t
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import OrganizationMembership


class ConversationGroupView(ConversationViewBase):
    """Перенос диалога в группу и снятие группы (ADR-CHATBALLS-0043 §3)."""

    required_capability = "conversations.transfer"

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
        conversation = move_conversation(context=request.tenant_context, conversation_id=conversation.id, group=group)
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

    required_capability = "conversations.assign"

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
                    user__is_active=True,
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
