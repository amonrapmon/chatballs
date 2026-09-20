from __future__ import annotations

import json
import urllib.error
import urllib.request

from django.conf import settings


class GatewayDeliveryError(RuntimeError):
    """Safe, retryable failure boundary for Chatballs-to-gateway handoff."""


def send_delivery_command(*, base_url: str, secret: str, command: dict) -> None:
    url = f"{base_url.rstrip('/')}/delivery-commands"
    try:
        body = json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise GatewayDeliveryError("gateway invalid command") from error

    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=settings.CHATBALLS_GATEWAY_DELIVERY_TIMEOUT_SECONDS
        ) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            if status != 202:
                raise GatewayDeliveryError("gateway unexpected HTTP status")
            try:
                response_body = json.loads(response.read().decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as error:
                raise GatewayDeliveryError("gateway invalid response") from error
    except GatewayDeliveryError:
        raise
    except urllib.error.HTTPError:
        raise GatewayDeliveryError("gateway unexpected HTTP status") from None
    except (OSError, TimeoutError, urllib.error.URLError):
        raise GatewayDeliveryError("gateway network failure") from None

    if (
        not isinstance(response_body, dict)
        or response_body.get("accepted") is not True
        or response_body.get("command_id") != command.get("command_id")
    ):
        raise GatewayDeliveryError("gateway invalid response")
