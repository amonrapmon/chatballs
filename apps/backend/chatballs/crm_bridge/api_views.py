"""Read-only API surface. Mutating endpoints follow in a separate reviewed stage."""

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api.permissions import HasCapability
from chatballs.conversations.models import Contact, Conversation
from chatballs.crm_bridge.models import (
    CRMCompany, CRMConnectionBinding, CRMOrganizationConfig, CRMProvider,
)
from chatballs.crm_bridge.resolution import links_for_contact, links_for_conversation


class CRMConfigurationView(APIView):
    permission_classes = [HasCapability]
    required_capability = "settings.view"

    def get(self, request: Request) -> Response:
        organization_id = request.tenant_context.organization_id
        provider = (
            CRMOrganizationConfig.objects.filter(organization_id=organization_id)
            .values_list("provider", flat=True).first() or CRMProvider.NONE
        )
        companies = CRMCompany.objects.filter(organization_id=organization_id).order_by("id")
        bindings = CRMConnectionBinding.objects.filter(organization_id=organization_id).order_by("id")
        return Response({
            "provider": provider,
            "companies": [{
                "id": company.id,
                "name": company.name,
                "externalCompanyId": company.external_company_id,
                "isPrimary": company.is_primary,
                "isActive": company.is_active,
            } for company in companies],
            "bindings": [{
                "integrationId": binding.integration_id,
                "companyId": binding.crm_company_id,
            } for binding in bindings],
        })


class CRMConversationLinkView(APIView):
    permission_classes = [HasCapability]
    required_capability = "conversations.view"

    def get(self, request: Request, conversation_id: int) -> Response:
        try:
            payload = links_for_conversation(
                context=request.tenant_context, conversation_id=conversation_id
            )
        except Conversation.DoesNotExist:
            return Response({"code": "not_found"}, status=404)
        return Response(payload)


class CRMContactLinksView(APIView):
    permission_classes = [HasCapability]
    required_capability = "customers.view"

    def get(self, request: Request, contact_id: int) -> Response:
        try:
            payload = links_for_contact(
                context=request.tenant_context, contact_id=contact_id
            )
        except Contact.DoesNotExist:
            return Response({"code": "not_found"}, status=404)
        return Response(payload)
