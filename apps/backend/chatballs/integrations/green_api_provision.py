"""Green API messenger onboarding through the native Integration + Channel model.

Only the authenticated Chatballs backend contacts the private adapter control
plane. Provider keys never enter Integration.config or frontend read APIs.
"""
from __future__ import annotations

import json
import os
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from chatballs.api.permissions import HasCapability
from chatballs.api_connector.outbound import configure_outbound, validate_command_url
from chatballs.api_connector.views import connector_event_path
from chatballs.identity.audit import record_audit_event
from chatballs.integrations.models import Integration, IntegrationProvider, IntegrationStatus
from chatballs.integrations.selectors import integration_for_context
from chatballs.integrations.serializers import integration_payload
from chatballs.tenancy.database import tenant_atomic


PROVIDERS = {
    "green_api_telegram": ("TG_GREEN_API", "TG"),
    "green_api_max": ("MAX_GREEN_API", "MAX"),
}


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _env_config(service: str) -> dict[str, str]:
    suffix = PROVIDERS[service][1]
    variables = {
        "privateUrl": os.environ.get(f"CHATBALLS_GREEN_{suffix}_PROVISION_URL", ""),
        "commandUrl": os.environ.get(f"CHATBALLS_GREEN_{suffix}_COMMAND_URL", ""),
        "token": os.environ.get(f"CHATBALLS_GREEN_{suffix}_PROVISION_TOKEN", ""),
        "publicBaseUrl": os.environ.get("CHATBALLS_CONNECTOR_PUBLIC_BASE_URL", ""),
    }
    if not all(variables.values()) or len(variables["token"]) < 32:
        raise ValueError("adapter_not_configured")
    url = urlsplit(variables["privateUrl"])
    if (url.scheme not in {"http", "https"} or not url.hostname or
            url.username or url.password or url.query or url.fragment or
            url.path != "/v1/provision"):
        raise ValueError("invalid_provision_endpoint")
    base = urlsplit(variables["publicBaseUrl"])
    if (base.scheme != "https" or not base.hostname or
            base.username or base.password or base.query or base.fragment or
            base.path not in {"", "/"}):
        raise ValueError("invalid_chatballs_origin")
    validate_command_url(variables["commandUrl"])
    return variables


def _api_origin(value: object) -> str:
    if not isinstance(value, str) or len(value) > 512:
        raise ValueError("invalid_provider_url")
    parsed = urlsplit(value)
    hostname = parsed.hostname or ""
    if (parsed.scheme != "https" or
            not (hostname == "green-api.com" or hostname.endswith(".green-api.com")) or
            parsed.username or parsed.password or parsed.query or parsed.fragment or
            parsed.path not in {"", "/"} or parsed.port not in {None, 443}):
        raise ValueError("invalid_provider_url")
    return f"https://{hostname}/"


def _request_adapter(config: dict[str, str], payload: dict) -> dict:
    serialized = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(serialized) > 16 * 1024:
        raise ValueError("credentials_too_large")
    request = Request(
        config["privateUrl"], method="POST", data=serialized,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['token']}",
        },
    )
    opener = build_opener(ProxyHandler({}), _NoRedirects())
    try:
        with opener.open(request, timeout=18) as response:
            if response.status != 200:
                raise RuntimeError("adapter_rejected")
            if int(response.headers.get("Content-Length") or "0") > 4096:
                raise RuntimeError("invalid_adapter_response")
            body = response.read(4097)
    except (HTTPError, URLError, OSError, TimeoutError) as error:
        # URL/body may carry secrets. Never echo exception text into API or logs.
        raise RuntimeError("adapter_unavailable_or_rejected") from error
    if len(body) > 4096:
        raise RuntimeError("invalid_adapter_response")
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError) as error:
        raise RuntimeError("invalid_adapter_response") from error
    if (not isinstance(data, dict) or data.get("configured") is not True or
            not isinstance(data.get("callbackUrl"), str) or
            not data["callbackUrl"].startswith("https://")):
        raise RuntimeError("invalid_adapter_response")
    return data


class GreenApiProvisionView(APIView):
    permission_classes = [HasCapability]
    required_capability = "integrations.manage"

    def post(self, request, integration_id: int) -> Response:
        data = request.data
        if not isinstance(data, dict):
            return Response({"error": "invalid_credentials"}, status=400)
        account = data.get("idInstance")
        provider_token = data.get("apiTokenInstance")
        if (not isinstance(account, str) or not account.isdigit() or
                len(account) > 20 or len(account) < 4 or
                not isinstance(provider_token, str) or
                not 8 <= len(provider_token) <= 1024 or any(c.isspace() for c in provider_token)):
            return Response({"error": "invalid_credentials"}, status=400)
        try:
            api_url = _api_origin(data.get("apiUrl"))
            media_url = _api_origin(data.get("mediaUrl"))
        except (ValueError, TypeError):
            return Response({"error": "invalid_provider_url"}, status=400)

        context = request.tenant_context
        with tenant_atomic(context):
            try:
                integration = integration_for_context(context=context, integration_id=integration_id)
            except Integration.DoesNotExist:
                return Response({"error": "not_found"}, status=404)
            service = integration.config.get("connector_service")
            if integration.provider != IntegrationProvider.API_CONNECTOR or service not in PROVIDERS:
                return Response({"error": "unsupported_connector_service"}, status=422)
            if not integration.is_active or not integration.channel_id or not integration.channel.is_active:
                return Response({"error": "channel_not_active"}, status=409)
            organization_public_id = str(context.organization.public_id)
            try:
                config = _env_config(service)
            except (ValueError, ValidationError):
                return Response({"error": "adapter_not_configured"}, status=503)

            # New ingress key is saved first so adapter /state/ can authenticate.
            ingress_token = secrets.token_urlsafe(48)
            integration.secret = ingress_token
            integration.status = IntegrationStatus.UNCHECKED
            integration.save(update_fields=["secret", "status", "updated_at"])

            command_token = secrets.token_urlsafe(48)
            callback_token = secrets.token_urlsafe(48)
            legacy_secret = secrets.token_urlsafe(48)
            base_url = config["publicBaseUrl"].rstrip("/") + "/"
            payload = {
                "service": PROVIDERS[service][0],
                "providerAccountId": account,
                "chatballsInstallationKey": base_url,
                "organizationPublicId": organization_public_id,
                "integrationId": integration.pk,
                "chatballsBaseUrl": config["publicBaseUrl"].rstrip("/"),
                "connectorWebhookPath": connector_event_path(organization_public_id, integration.pk),
                "commandToken": command_token,
                "callbackSecret": callback_token,
                "credentials": {
                    "providerToken": provider_token,
                    "connectorIngressToken": ingress_token,
                    "integrationSecret": legacy_secret,
                },
                "settings": {
                    "providerApiUrl": api_url,
                    "providerMediaUrl": media_url,
                    "downloadHostnames": [urlsplit(media_url).hostname],
                    "callbackId": "green-api-" + account,
                    "mediaLifecycleEnabled": False,
                    "requestTimeoutMs": 10000,
                },
            }

        # Do not keep tenant database transactions open across network requests.
        try:
            result = _request_adapter(config, payload)
        except (RuntimeError, ValueError):
            return Response({"error": "adapter_provision_failed", "retryable": True}, status=502)

        with tenant_atomic(context):
            integration = integration_for_context(context=context, integration_id=integration_id)
            if integration.secret != ingress_token or integration.config.get("connector_service") != service:
                return Response({"error": "integration_changed_retry"}, status=409)
            configure_outbound(integration, url=config["commandUrl"], token=command_token)
            integration.config = {
                **integration.config,
                "callback_url": result["callbackUrl"],
            }
            integration.status = IntegrationStatus.OK
            integration.last_error = ""
            integration.last_error_code = ""
            integration.last_checked_at = timezone.now()
            integration.save(update_fields=[
                "config", "status", "last_error", "last_error_code",
                "last_checked_at", "updated_at",
            ])
            record_audit_event(
                action="integrations.green_api_provisioned",
                actor=request.user, organization=context.organization,
                object_type="Integration", object_id=str(integration.pk),
                request=request,
            )
            response = Response({
                "integration": integration_payload(integration),
                "callbackUrl": result["callbackUrl"],
                "note": "GREEN_API_SETTINGS_MAY_TAKE_5_MINUTES",
            })
            response["Cache-Control"] = "no-store"
            return response
