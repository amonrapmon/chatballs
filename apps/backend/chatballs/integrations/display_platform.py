"""Operator-facing messenger platform, independent of the transport.

An API Connector remains API_CONNECTOR for routing and credentials. Its
connector_service only selects the visual platform exposed to operator APIs.
"""

from chatballs.integrations.models import Integration, IntegrationProvider

CONNECTOR_PLATFORM_BY_SERVICE = {
    "green_api_telegram": IntegrationProvider.TELEGRAM,
    "green_api_max": IntegrationProvider.MAX,
    "green_api_vk": IntegrationProvider.VK,
}


def display_provider(integration: Integration | None) -> str | None:
    if integration is None:
        return None
    if integration.provider != IntegrationProvider.API_CONNECTOR:
        return integration.provider
    config = integration.config if isinstance(integration.config, dict) else {}
    return CONNECTOR_PLATFORM_BY_SERVICE.get(
        config.get("connector_service"), IntegrationProvider.API_CONNECTOR
    )
