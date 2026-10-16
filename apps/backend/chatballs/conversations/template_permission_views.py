"""OWNER/ADMIN grant shared-library management without changing roles."""

from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api.permissions import HasCapability
from chatballs.conversations.template_access import can_manage_shared
from chatballs.conversations.template_models import ReplyTemplateManagementGrant
from chatballs.conversations.template_validation import LibraryValidationError
from chatballs.i18n import t
from chatballs.identity.audit import record_audit_event
from chatballs.identity.models import OrganizationMembership
from chatballs.identity.policy import can_administer_access


class TemplatePermissionsView(APIView):
    permission_classes = [HasCapability]
    required_capability = "conversations.view"

    def get(self, request):
        actor = request.tenant_context.membership
        return Response({
            "canManageShared": can_manage_shared(actor),
            "canGrantSharedManagement": can_administer_access(actor),
        })


class TemplateManagementGrantView(APIView):
    permission_classes = [HasCapability]
    required_capability = "conversations.view"

    def target(self, request, membership_id):
        if not can_administer_access(request.tenant_context.membership):
            raise PermissionDenied(t("conversations.template_management_denied"))
        try:
            return OrganizationMembership.objects.get(
                organization_id=request.tenant_context.organization_id, pk=membership_id,
            )
        except OrganizationMembership.DoesNotExist:
            raise NotFound(t("admin.employee_not_found")) from None

    def get(self, request, membership_id):
        target = self.target(request, membership_id)
        return Response({
            "membershipId": target.pk, "canManageShared": can_manage_shared(target),
            "granted": ReplyTemplateManagementGrant.objects.filter(membership=target).exists(),
        })

    @transaction.atomic
    def patch(self, request, membership_id):
        target = self.target(request, membership_id)
        granted = request.data.get("granted")
        if type(granted) is not bool or set(request.data) != {"granted"}:
            raise LibraryValidationError(t("conversations.template_grant_invalid"))
        if granted:
            ReplyTemplateManagementGrant.objects.get_or_create(
                organization_id=target.organization_id, membership=target,
            )
        else:
            ReplyTemplateManagementGrant.objects.filter(membership=target).delete()
        record_audit_event(
            action="conversations.template_management_changed",
            actor=request.user, organization=request.tenant_context.organization,
            object_type="OrganizationMembership", object_id=str(target.pk),
            payload={"granted": granted}, request=request,
        )
        return Response({"membershipId": target.pk, "granted": granted, "canManageShared": can_manage_shared(target)})
