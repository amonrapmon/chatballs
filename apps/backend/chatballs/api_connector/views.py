"""Authenticated, tenant-scoped ingress for initial text-only Connector v1.

Media, receipt, echo, and outbound command endpoints are deliberately absent
until their durable semantics are implemented and contract-tested.
"""
from __future__ import annotations

import json
import secrets

from django.urls import reverse
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api_connector.payloads import ConnectorPayloadError, parse_text_event
from chatballs.conversations.ingest import ingest_inbound
from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.tenancy.database import tenant_atomic
from chatballs.tenancy.ingress import organization_route_by_public_id
from chatballs.tenancy.lookup import load_organization

MAX_EVENT_BODY_BYTES = 64 * 1024


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError("invalid_json_number")


def _parse_json_bytes(raw: bytes) -> object:
    return json.loads(
        raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys,
        parse_constant=_reject_nonfinite,
    )


class ConnectorEventView(APIView):
    # The external adapter uses a per-Integration Bearer, not Django session auth.
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request: Request, connector_organization_public_id, integration_id: int) -> Response:
        if request.content_type != "application/json":
            return Response({"error": "invalid_payload"}, status=400)
        if request._request.META.get("CONTENT_LENGTH", "").isdigit():
            if int(request._request.META["CONTENT_LENGTH"]) > MAX_EVENT_BODY_BYTES:
                return Response({"error": "payload_too_large"}, status=413)
        raw = request._request.body
        if len(raw) > MAX_EVENT_BODY_BYTES:
            return Response({"error": "payload_too_large"}, status=413)

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

            token = request.headers.get("Authorization", "")
            expected = f"Bearer {integration.secret}"
            if not integration.secret or len(token) > 1024 or not secrets.compare_digest(token, expected):
                return Response({"error": "unauthorized"}, status=401)
            if not integration.is_active or not integration.channel or not integration.channel.is_active:
                return Response({"error": "forbidden"}, status=403)

            try:
                payload = _parse_json_bytes(raw)
            except (ValueError, UnicodeDecodeError):
                return Response({"error": "invalid_payload"}, status=400)
            try:
                parsed = parse_text_event(payload)
            except ConnectorPayloadError as error:
                return Response({"error": error.code}, status=error.status)

            expected_source = f"connection-{integration.id}"
            if parsed.source_id != expected_source:
                return Response({"error": "source_mismatch"}, status=409)
            try:
                ingest_inbound(
                    integration, parsed.inbound,
                    connector_event_id=parsed.event_id,
                    connector_fingerprint=parsed.fingerprint,
                )
            except ValueError as error:
                if str(error) == "connector_event_id_conflict":
                    return Response({"error": "id_conflict"}, status=409)
                raise
        return Response({"accepted": True, "id": parsed.event_id}, status=202)


def connector_event_path(organization_public_id, integration_id: int) -> str:
    return reverse(
        "api-connector-events",
        kwargs={"connector_organization_public_id": organization_public_id, "integration_id": integration_id},
    )
