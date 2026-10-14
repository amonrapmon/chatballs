"""Policy settings and history guarded by current conversation access."""

from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api.pagination import page_payload, paginate
from chatballs.api.permissions import HasCapability
from chatballs.conversations.assignment_policy import (
    AssignmentPolicy,
    policy_payload,
    validate_policy,
)
from chatballs.conversations.models import Conversation
from chatballs.conversations.transfer_display import transfer_history_payload
from chatballs.conversations.transfer_models import ConversationTransfer, TransferReason
from chatballs.conversations.transfer_services import require_reason_management
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.i18n import t
from chatballs.identity.models import Organization
from chatballs.tenancy.database import tenant_atomic


class AssignmentPolicyView(APIView):
    permission_classes = [HasCapability]
    required_capability = "settings.manage"

    def get(self, request):
        require_reason_management(request.tenant_context)
        policy = AssignmentPolicy.objects.filter(organization_id=request.tenant_context.organization_id).first()
        return Response({"allowedStatuses": policy_payload(policy) if policy else None})

    def put(self, request):
        context = request.tenant_context
        require_reason_management(context)
        clean = validate_policy(request.data)
        with tenant_atomic(context):
            Organization.objects.select_for_update().get(pk=context.organization_id)
            policy, _ = AssignmentPolicy.objects.update_or_create(
                organization_id=context.organization_id, defaults=clean,
            )
        return Response({"allowedStatuses": policy_payload(policy)})


class TransferHistoryView(ConversationViewBase):
    def get(self, request, conversation_id, transfer_id=None):
        try:
            conversation = self._conversation(request, conversation_id)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        rows = ConversationTransfer.objects.filter(
            organization_id=request.tenant_context.organization_id, conversation=conversation,
        ).select_related(
            "reason", "initiated_by", "previous_operator", "new_operator",
            "conversation__contact", "conversation__connection",
        ).order_by("-occurred_at", "-id")
        if transfer_id is not None:
            row = rows.filter(pk=transfer_id).first()
            if row is None:
                return Response({"detail": t("conversations.not_found")}, status=404)
            return Response({"transfer": transfer_history_payload(row)})
        return Response(page_payload(paginate(rows, request.query_params), transfer_history_payload))


class TransferOptionsView(ConversationViewBase):
    required_capability = "conversations.assign"

    def get(self, request, conversation_id):
        try:
            self._conversation(request, conversation_id, self.required_capability)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        reasons = TransferReason.objects.filter(
            organization_id=request.tenant_context.organization_id, is_active=True,
        )
        from chatballs.conversations.transfer_reason_views import reason_option_payload

        return Response(page_payload(paginate(reasons, request.query_params), reason_option_payload))
