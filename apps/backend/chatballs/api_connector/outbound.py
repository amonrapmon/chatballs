"""Durable, source-scoped operator text commands to an independent adapter.

Adapter HTTP 200/202 acknowledges only durable COMMAND ACCEPTANCE, never
provider delivery. Outbox replay uses a stable command ID and immutable route.
"""
from __future__ import annotations

import hashlib
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import NAMESPACE_URL, uuid5

from django.core.exceptions import ValidationError
from django.utils import timezone

from chatballs.conversations.models import Message
from chatballs.events.services import DomainEvent, enqueue_event
from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.integrations.outbound import HTTP_SCHEMES, OutboundUrlRejected, clean_config_url
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic

CONNECTOR_OUTBOUND_REQUESTED = "conversations.api_connector_outbound_requested"
MAX_COMMAND_BODY_BYTES = 16 * 1024


class _NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def validate_command_url(value: object) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise ValidationError({"url": "Invalid adapter command URL"})
    try:
        url = clean_config_url(value, schemes=HTTP_SCHEMES)
        parsed = urlsplit(url)
        _ = parsed.port
    except (OutboundUrlRejected, ValueError) as error:
        raise ValidationError({"url": "Invalid adapter command URL"}) from error
    if (url != value or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path != "/v1/commands"):
        raise ValidationError({"url": "Use the adapter /v1/commands URL without credentials or query"})
    # Unencrypted Bearer is permitted only for local independent adapter testing.
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "::1", "localhost"}
    ):
        raise ValidationError({"url": "HTTPS is required for non-local adapter commands"})
    return url


def outbound_token(connection: Integration) -> str:
    try:
        value = json.loads(connection.secret_headers or "{}")
    except (TypeError, ValueError):
        return ""
    return value.get("connector_command_token", "") if isinstance(value, dict) else ""


def outbound_available(connection: Integration) -> bool:
    if (connection.provider != IntegrationProvider.API_CONNECTOR or not connection.is_active
            or not connection.channel_id or not connection.channel.is_active):
        return False
    if not outbound_token(connection):
        return False
    try:
        validate_command_url(connection.config.get("command_url", ""))
    except ValidationError:
        return False
    return True


def configure_outbound(connection: Integration, *, url: object, token: object) -> None:
    if connection.provider != IntegrationProvider.API_CONNECTOR:
        raise ValidationError({"provider": "Unsupported integration provider"})
    url = validate_command_url(url)
    if (not isinstance(token, str) or not 16 <= len(token) <= 1024
            or any(c.isspace() for c in token)):
        raise ValidationError({"token": "Adapter Bearer token must be 16-1024 non-whitespace characters"})
    connection.config = {**connection.config, "command_url": url}
    # EncryptedCharField. Never put credentials in config or OutboxEvent.
    connection.secret_headers = json.dumps({"connector_command_token": token})
    connection.save(update_fields=["config", "secret_headers", "updated_at"])


def queue_operator_text(*, context: TenantContext, conversation, message: Message) -> None:
    _queue_operator_command(
        context=context, conversation=conversation, message=message,
        payload={"kind": "text", "text": message.text, "media": []},
    )


def queue_operator_file(
    *, context: TenantContext, conversation, message: Message, content: bytes,
) -> None:
    """Queue ONE native operator attachment. No bytes or fetch URL in Outbox."""
    connection = conversation.connection
    if connection is None or connection.config.get("connectorMediaOutboundEnabled") is not True:
        raise ValidationError({"detail": "Connector outbound media is not enabled"})
    if not message.attachment or not content:
        raise ValidationError({"detail": "Missing native operator attachment"})
    from chatballs.conversations.attachment_policy import MAX_FILE_BYTES
    if len(content) > MAX_FILE_BYTES or len(content) != message.attachment_size:
        raise ValidationError({"detail": "Invalid native attachment size"})
    _queue_operator_command(
        context=context, conversation=conversation, message=message,
        payload={
            "kind": "file", "text": message.text,
            "media": [{
                "ref": "command",  # Resolved from authenticated command_id, never from a URL
                "filename": message.attachment_name,
                "content_type": message.attachment_content_type,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }],
        },
    )


def _queue_operator_command(
    *, context: TenantContext, conversation, message: Message, payload: dict,
) -> None:
    connection = conversation.connection
    if connection is None or not outbound_available(connection):
        raise ValidationError({"detail": "Adapter command transport is not configured"})
    chat_id = conversation.external_chat_id
    user_id = conversation.route_external_user_id
    if not chat_id or not user_id or len(chat_id) > 128 or len(user_id) > 128:
        raise ValidationError({"detail": "Conversation has no stable connector route"})
    command_id = str(uuid5(NAMESPACE_URL, f"chatballs-api-connector:message:{message.pk}"))
    command = {
        "schema": "chatballs.api-connector.command.v1",
        "source_id": f"connection-{connection.pk}",
        "command_id": command_id,
        "recipient": {"external_chat_id": chat_id, "external_user_id": user_id},
        "route_version": "source-scoped-route-v1",
        "created_at": message.created_at.isoformat(),
        "message": payload,
    }
    message.connector_delivery = {"state": "QUEUED", "commandId": command_id}
    message.save(update_fields=["connector_delivery"])
    enqueue_event(DomainEvent(
        aggregate_type="api_connector_conversation",
        aggregate_id=str(conversation.pk),
        event_type=CONNECTOR_OUTBOUND_REQUESTED,
        payload={
            "message_id": message.pk, "integration_id": connection.pk,
            "command_url": connection.config["command_url"], "command": command,
        },
        tenant_context=TenantContext.for_resource(context.organization),
    ))


def _send_command(url: str, token: str, command: dict) -> None:
    encoded = json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_COMMAND_BODY_BYTES:
        raise RuntimeError("connector_command_too_large")
    request = Request(
        url, data=encoded, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with build_opener(_NoRedirects()).open(request, timeout=8) as response:
            if response.status not in {200, 202}:
                raise RuntimeError("connector_adapter_rejected")
            try:
                receipt = json.loads(response.read(4097))
            except (ValueError, UnicodeDecodeError) as error:
                raise RuntimeError("connector_adapter_invalid_ack") from error
            if (not isinstance(receipt, dict) or len(json.dumps(receipt)) > 4096
                    or receipt.get("accepted") is not True
                    or receipt.get("id") != command["command_id"]):
                raise RuntimeError("connector_adapter_invalid_ack")
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        # Never put URL, Authorization, response body or provider PII in outbox errors.
        raise RuntimeError("connector_adapter_unavailable") from error


def deliver_connector_command(payload: dict, context: TenantContext) -> None:
    # Never hold a tenant DB transaction over external HTTP.
    with tenant_atomic(context):
        message = Message.objects.select_related("conversation__connection__channel").filter(
            pk=payload["message_id"], organization_id=context.organization_id,
            author_type="OPERATOR",
        ).first()
        if message is None:
            raise RuntimeError("connector_message_missing")
        connection = message.conversation.connection
        command = payload["command"]
        delivery = message.connector_delivery or {}
        if delivery.get("state") in {"ADAPTER_ACCEPTED", "PROVIDER_SENT", "DELIVERED", "FAILED"}:
            return
        if (connection is None or connection.pk != payload["integration_id"]
                or delivery.get("commandId") != command.get("command_id")
                or not outbound_available(connection)
                or connection.config.get("command_url") != payload["command_url"]):
            raise RuntimeError("connector_route_unavailable")
        token = outbound_token(connection)
        url = connection.config["command_url"]

    _send_command(url, token, command)

    with tenant_atomic(context):
        message = Message.objects.select_for_update().get(
            pk=payload["message_id"], organization_id=context.organization_id,
        )
        if message.connector_delivery.get("commandId") != command["command_id"]:
            raise RuntimeError("connector_command_changed")
        # A provider receipt may race ahead of the HTTP adapter ACK.
        # Preserve confirmed provider/terminal status rather than regressing it.
        if message.connector_delivery.get("state") == "QUEUED":
            message.connector_delivery = {
                **message.connector_delivery,
                "state": "ADAPTER_ACCEPTED",
                "acceptedAt": timezone.now().isoformat(),
            }
            message.save(update_fields=["connector_delivery"])
