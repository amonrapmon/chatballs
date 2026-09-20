from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from chatballs.conversations.ingest import ingest_inbound
from chatballs.identity.models import Organization
from chatballs.integrations.models import Integration
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic
from chatballs.tenancy.ingress import gateway_integration_route
from chatballs.tenancy.lookup import load_organization

from .payloads import (
    GatewayPayloadError,
    UnsupportedGatewayChatError,
    parse_inbound_payload,
)
from .security import (
    GatewayIngressError,
    authenticate_gateway_request,
    ensure_gateway_provider,
    ensure_gateway_runtime,
)

T = TypeVar("T")


def gateway_authenticated_request(
    *,
    integration_id: int,
    authorization: str,
    operation: Callable[[TenantContext, Integration], T],
) -> T:
    route = gateway_integration_route(integration_id)
    if route is None:
        raise GatewayIngressError(404, "Gateway integration not found")
    organization: Organization | None = load_organization(route.organization_id)
    if organization is None:
        raise GatewayIngressError(404, "Gateway integration not found")

    context = TenantContext.for_resource(organization)
    with tenant_atomic(context):
        integration = (
            Integration.objects.select_related("channel")
            .filter(id=integration_id, organization_id=context.organization_id)
            .first()
        )
        if integration is None:
            raise GatewayIngressError(404, "Gateway integration not found")
        ensure_gateway_provider(integration)
        authenticate_gateway_request(integration, authorization)
        ensure_gateway_runtime(integration)
        return operation(context, integration)


def accept_gateway_inbound(*, integration_id: int, authorization: str, payload: object) -> None:
    def accept(context: TenantContext, integration: Integration) -> None:
        try:
            parsed = parse_inbound_payload(payload)
        except UnsupportedGatewayChatError as error:
            raise GatewayIngressError(422, str(error)) from error
        except GatewayPayloadError as error:
            raise GatewayIngressError(400, str(error)) from error

        if parsed.source_id != str(integration.config.get("source_id", "")):
            raise GatewayIngressError(409, "Gateway source_id does not match integration")

        ingest_inbound(integration, parsed.inbound)

    gateway_authenticated_request(
        integration_id=integration_id,
        authorization=authorization,
        operation=accept,
    )
