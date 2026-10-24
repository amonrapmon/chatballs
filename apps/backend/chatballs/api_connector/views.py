"""Authenticated, tenant-scoped Connector event and receipt ingress.

JSON text and receipts retain their v1 contract; opt-in binary file events
enter native Chatballs ingest through the same authenticated integration route.
"""
from __future__ import annotations

import json
import secrets

from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.permissions import AllowAny
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api.permissions import HasCapability
from chatballs.api_connector.outbound import configure_outbound, outbound_available
from chatballs.api_connector.media import MAX_MULTIPART_BODY_BYTES, parse_multipart_event
from chatballs.api_connector.payloads import ConnectorPayloadError, parse_text_event
from chatballs.api_connector.receipts import apply_delivery_receipt, parse_delivery_receipt
from chatballs.conversations.ingest import ingest_inbound
from chatballs.identity.audit import record_audit_event
from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.integrations.selectors import integration_for_context
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
    parser_classes = [JSONParser, MultiPartParser]

    def post(self, request: Request, connector_organization_public_id, integration_id: int) -> Response:
        is_media = request.content_type == "multipart/form-data"
        if not is_media and request.content_type != "application/json":
            return Response({"error": "invalid_payload"}, status=400)
        length = request._request.META.get("CONTENT_LENGTH", "")
        if is_media:
            # Reject early before any multipart parser/upload handler starts.
            if not length.isdecimal():
                return Response({"error": "invalid_payload"}, status=400)
            if int(length) > MAX_MULTIPART_BODY_BYTES:
                return Response({"error": "payload_too_large"}, status=413)
            raw = b""
        else:
            if length.isdigit() and int(length) > MAX_EVENT_BODY_BYTES:
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

            if is_media:
                # Off by default, never parse or accept a binary file until enabled.
                if integration.config.get("connectorMediaInboundEnabled") is not True:
                    return Response({"error": "unsupported_capability"}, status=422)
                try:
                    parsed = parse_multipart_event(request, decode_json=_parse_json_bytes)
                except ConnectorPayloadError as error:
                    return Response({"error": error.code}, status=error.status)
            else:
                try:
                    payload = _parse_json_bytes(raw)
                except (ValueError, UnicodeDecodeError):
                    return Response({"error": "invalid_payload"}, status=400)
                if isinstance(payload, dict) and payload.get("schema") == "chatballs.api-connector.receipt.v1":
                    try:
                        receipt = parse_delivery_receipt(payload)
                        apply_delivery_receipt(integration, receipt)
                    except ConnectorPayloadError as error:
                        return Response({"error": error.code}, status=error.status)
                    return Response({"accepted": True, "id": receipt.event_id}, status=202)
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
            except OSError:
                if not is_media:
                    raise
                # Native storage errors must never become accepted placeholders.
                return Response({"error": "storage_unavailable"}, status=503)
        return Response({"accepted": True, "id": parsed.event_id}, status=202)


def connector_event_path(organization_public_id, integration_id: int) -> str:
    return reverse(
        "api-connector-events",
        kwargs={"connector_organization_public_id": organization_public_id, "integration_id": integration_id},
    )


class ConnectorTransportView(APIView):
    """Admin-only callback destination and encrypted adapter command credential."""

    permission_classes = [HasCapability]
    required_capability = "integrations.manage"

    def post(self, request: Request, integration_id: int) -> Response:
        try:
            integration = integration_for_context(
                context=request.tenant_context, integration_id=integration_id,
            )
        except Integration.DoesNotExist:
            return Response({"error": "not_found"}, status=404)
        if integration.provider != IntegrationProvider.API_CONNECTOR:
            return Response({"error": "unsupported_provider"}, status=422)
        try:
            configure_outbound(
                integration, url=request.data.get("url"), token=request.data.get("token"),
            )
        except ValidationError as error:
            return Response({"errors": error.message_dict}, status=400)
        record_audit_event(
            action="integrations.connector_transport_configured",
            actor=request.user,
            organization=request.tenant_context.organization,
            object_type="Integration", object_id=str(integration.pk),
            request=request,
        )
        response = Response({"configured": outbound_available(integration)})
        response["Cache-Control"] = "no-store"
        return response
