"""Authenticated read-only Integration state for external Connector runtimes.

Adapter credentials are never returned. The inbound Integration Bearer proves
the caller belongs to this Integration; the path only selects the tenant.
"""

from __future__ import annotations

import secrets

from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.identity.models import Organization
from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.tenancy.database import tenant_atomic
from chatballs.tenancy.ingress import organization_route_by_public_id
from chatballs.tenancy.lookup import load_organization


class ConnectorIntegrationStateView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request: Request, connector_organization_public_id, integration_id: int) -> Response:
        route = organization_route_by_public_id(str(connector_organization_public_id))
        if route is None:
            return Response({"error": "not_found"}, status=404)
        organization: Organization | None = load_organization(route.organization_id)
        if organization is None:
            return Response({"error": "not_found"}, status=404)

        with tenant_atomic(organization.id):
            integration = Integration.objects.select_related("channel").filter(
                pk=integration_id, organization=organization,
                provider=IntegrationProvider.API_CONNECTOR,
            ).first()
            if integration is None:
                return Response({"error": "not_found"}, status=404)
            supplied = request.headers.get("Authorization", "")
            expected = f"Bearer {integration.secret}"
            if not integration.secret or len(supplied) > 1024 or not secrets.compare_digest(supplied, expected):
                return Response({"error": "unauthorized"}, status=401)
            active = bool(
                integration.is_active
                and integration.channel_id
                and integration.channel.is_active
            )
            result = Response({
                "sourceId": f"connection-{integration.pk}",
                "active": active,
                "connectorService": integration.config.get("connector_service", ""),
                "revision": integration.updated_at.isoformat(),
            })
            result["Cache-Control"] = "no-store"
            return result
