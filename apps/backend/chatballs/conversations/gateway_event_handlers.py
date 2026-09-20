from __future__ import annotations

from chatballs.conversations.gateway_delivery import GATEWAY_DELIVERY_COMMAND_REQUESTED
from chatballs.conversations.gateway_http import GatewayDeliveryError, send_delivery_command
from chatballs.events.handlers import register
from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


def _gateway_connection_details(
    *, payload: dict, context: TenantContext
) -> tuple[str, str, dict]:
    integration_id = payload.get("integration_id")
    command = payload.get("command")
    if not isinstance(integration_id, int) or isinstance(integration_id, bool):
        raise GatewayDeliveryError("gateway invalid integration")
    if not isinstance(command, dict):
        raise GatewayDeliveryError("gateway invalid command")
    command_source_id = command.get("source_id")
    if not isinstance(command_source_id, str) or not command_source_id:
        raise GatewayDeliveryError("gateway invalid command")

    with tenant_atomic(context):
        integration = (
            Integration.objects.filter(
                pk=integration_id,
                organization_id=context.organization_id,
                provider=IntegrationProvider.GATEWAY,
                is_active=True,
            )
            .first()
        )
        if integration is None:
            raise GatewayDeliveryError("gateway integration unavailable")
        config = integration.config if isinstance(integration.config, dict) else {}
        base_url = config.get("base_url")
        source_id = config.get("source_id")
        secret = integration.secret
        if not isinstance(base_url, str) or not base_url:
            raise GatewayDeliveryError("gateway integration unavailable")
        if not isinstance(source_id, str) or not source_id:
            raise GatewayDeliveryError("gateway integration unavailable")
        if not isinstance(secret, str) or not secret:
            raise GatewayDeliveryError("gateway integration unavailable")
        if command_source_id != source_id:
            raise GatewayDeliveryError("gateway source mismatch")
        return base_url, secret, command


@register(
    GATEWAY_DELIVERY_COMMAND_REQUESTED,
    tenant_transaction=False,
    recover_stale_processing=True,
)
def handle_gateway_delivery_command_requested(
    payload: dict, context: TenantContext | None
) -> None:
    if context is None:
        raise GatewayDeliveryError("gateway tenant context missing")
    if not isinstance(payload, dict):
        raise GatewayDeliveryError("gateway invalid payload")
    base_url, secret, command = _gateway_connection_details(payload=payload, context=context)
    send_delivery_command(base_url=base_url, secret=secret, command=command)
