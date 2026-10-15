"""Write endpoints: existing tenant capability checks and atomic audit."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api.permissions import HasCapability
from chatballs.crm_bridge.services import (
    CRMConfigurationError, create_company, delete_binding, delete_company,
    set_binding, set_provider, update_company,
)
from chatballs.identity.audit import record_audit_event


def _error(error: CRMConfigurationError) -> Response:
    return Response({"code": error.code}, status=error.status)


def _company_payload(company) -> dict:
    return {
        "id": company.id,
        "name": company.name,
        "externalCompanyId": company.external_company_id,
        "isPrimary": company.is_primary,
        "isActive": company.is_active,
    }


def _audit(request: Request, action: str, object_type: str, object_id: str) -> None:
    record_audit_event(
        action=action, actor=request.user,
        organization=request.tenant_context.organization,
        object_type=object_type, object_id=object_id,
        request=request,
    )


def _execute(operation):
    try:
        return operation()
    except CRMConfigurationError as error:
        return _error(error)
    except ValidationError:
        return Response({"code": "invalid_configuration"}, status=400)
    except IntegrityError:
        return Response({"code": "configuration_conflict"}, status=409)


class CRMProviderUpdateView(APIView):
    permission_classes = [HasCapability]
    required_capability = "settings.manage"

    def patch(self, request: Request) -> Response:
        if not isinstance(request.data, dict) or set(request.data) != {"provider"}:
            return Response({"code": "invalid_provider_update"}, status=400)

        def operation():
            with transaction.atomic():
                config, changed = set_provider(
                    organization_id=request.tenant_context.organization_id,
                    provider=request.data["provider"],
                )
                if changed:
                    _audit(request, "administration.crm_provider_updated",
                           "CRMOrganizationConfig", str(config.id))
                return Response({"provider": config.provider})

        return _execute(operation)


class CRMCompanyListWriteView(APIView):
    permission_classes = [HasCapability]
    required_capability = "settings.manage"

    def post(self, request: Request) -> Response:
        data = request.data
        if not isinstance(data, dict) or set(data) - {"name", "externalCompanyId", "isPrimary", "isActive"}:
            return Response({"code": "invalid_company_update"}, status=400)

        def operation():
            with transaction.atomic():
                company = create_company(
                    organization_id=request.tenant_context.organization_id,
                    name=data.get("name"),
                    external_company_id=data.get("externalCompanyId"),
                    is_primary=data.get("isPrimary", False),
                    is_active=data.get("isActive", True),
                )
                _audit(request, "administration.crm_company_created", "CRMCompany", str(company.pk))
                return Response({"company": _company_payload(company)}, status=201)

        return _execute(operation)


class CRMCompanyWriteView(APIView):
    permission_classes = [HasCapability]
    required_capability = "settings.manage"

    def patch(self, request: Request, company_id: int) -> Response:
        if not isinstance(request.data, dict):
            return Response({"code": "invalid_company_update"}, status=400)

        def operation():
            with transaction.atomic():
                company, changed = update_company(
                    organization_id=request.tenant_context.organization_id,
                    company_id=company_id, changes=request.data,
                )
                if changed:
                    _audit(request, "administration.crm_company_updated", "CRMCompany", str(company.pk))
                return Response({"company": _company_payload(company)})

        return _execute(operation)

    def delete(self, request: Request, company_id: int) -> Response:
        def operation():
            with transaction.atomic():
                delete_company(
                    organization_id=request.tenant_context.organization_id, company_id=company_id
                )
                _audit(request, "administration.crm_company_deleted", "CRMCompany", str(company_id))
                return Response(status=204)

        return _execute(operation)


class CRMBindingWriteView(APIView):
    permission_classes = [HasCapability]
    required_capability = "settings.manage"

    def put(self, request: Request, integration_id: int) -> Response:
        if not isinstance(request.data, dict) or set(request.data) != {"companyId"}:
            return Response({"code": "invalid_binding_update"}, status=400)

        def operation():
            with transaction.atomic():
                binding, changed = set_binding(
                    organization_id=request.tenant_context.organization_id,
                    integration_id=integration_id, company_id=request.data["companyId"],
                )
                if changed:
                    _audit(request, "administration.crm_binding_updated",
                           "CRMConnectionBinding", str(binding.pk))
                return Response({
                    "integrationId": binding.integration_id,
                    "companyId": binding.crm_company_id,
                })

        return _execute(operation)

    def delete(self, request: Request, integration_id: int) -> Response:
        def operation():
            with transaction.atomic():
                changed = delete_binding(
                    organization_id=request.tenant_context.organization_id,
                    integration_id=integration_id,
                )
                if changed:
                    _audit(request, "administration.crm_binding_deleted",
                           "Integration", str(integration_id))
                return Response(status=204)

        return _execute(operation)
