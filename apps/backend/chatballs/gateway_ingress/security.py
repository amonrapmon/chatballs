from __future__ import annotations

import secrets

from chatballs.integrations.models import Integration, IntegrationProvider


class GatewayIngressError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__(detail)


def authenticate_gateway_request(integration: Integration, authorization: str) -> None:
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        raise GatewayIngressError(401, "Bearer authentication is required")
    token = authorization[len(prefix) :]
    if not token or not secrets.compare_digest(str(integration.secret), token):
        raise GatewayIngressError(401, "Invalid gateway credentials")


def ensure_gateway_provider(integration: Integration) -> None:
    if integration.provider != IntegrationProvider.GATEWAY:
        raise GatewayIngressError(404, "Gateway integration not found")


def ensure_gateway_runtime(integration: Integration) -> None:
    if not integration.is_active:
        raise GatewayIngressError(409, "Gateway integration is inactive")
    channel = integration.channel
    if channel is None or not channel.is_active:
        raise GatewayIngressError(409, "Gateway channel is inactive")
