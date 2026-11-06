"""Integration-scoped access to an existing native operator attachment.

The adapter requests bytes by the same durable command ID it accepted.
No signed URLs, public media endpoints, provider credentials, or new storage.
"""
from __future__ import annotations

import secrets

from django.http import FileResponse
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.conversations.models import Message, MessageAuthor, MessageKind
from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.tenancy.database import tenant_atomic
from chatballs.tenancy.ingress import organization_route_by_public_id
from chatballs.tenancy.lookup import load_organization


class ConnectorCommandAttachmentView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(
        self, request: Request, connector_organization_public_id,
        integration_id: int, command_id,
    ):
        route = organization_route_by_public_id(str(connector_organization_public_id))
        if route is None:
            return Response({"error": "not_found"}, status=404)
        organization = load_organization(route.organization_id)
        if organization is None:
            return Response({"error": "not_found"}, status=404)

        with tenant_atomic(organization.id):
            integration = Integration.objects.select_related("channel").filter(
                pk=integration_id,
                organization=organization,
                provider=IntegrationProvider.API_CONNECTOR,
            ).first()
            if integration is None:
                return Response({"error": "not_found"}, status=404)
            provided = request.headers.get("Authorization", "")
            expected = f"Bearer {integration.secret}"
            if (not integration.secret or len(provided) > 1024
                    or not secrets.compare_digest(provided, expected)):
                return Response({"error": "unauthorized"}, status=401)
            if (not integration.is_active or not integration.channel
                    or not integration.channel.is_active):
                return Response({"error": "forbidden"}, status=403)
            if integration.config.get("connectorMediaOutboundEnabled") is not True:
                return Response({"error": "unsupported_capability"}, status=422)

            message = (
                Message.objects.filter(
                    organization_id=organization.id,
                    conversation__connection=integration,
                    author_type=MessageAuthor.OPERATOR,
                    kind=MessageKind.FILE,
                    connector_delivery__commandId=str(command_id),
                )
                .first()
            )
            if message is None or not message.attachment:
                return Response({"error": "not_found"}, status=404)

            response = FileResponse(
                message.attachment.open("rb"),
                content_type=message.attachment_content_type,
                as_attachment=True,
                filename=message.attachment_name,
            )
            response["Cache-Control"] = "private, no-store"
            response["X-Content-Type-Options"] = "nosniff"
            return response
