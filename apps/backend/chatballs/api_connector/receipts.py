"""Authenticated, source-scoped, idempotent provider delivery receipts.

A receipt is a claim by the trusted adapter, not inferred from an HTTP ACK.
Terminal states are immutable; lower-ranked arrivals cannot downgrade delivery.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from django.utils import timezone

from chatballs.api_connector.payloads import (
    ConnectorPayloadError,
    _identifier,
    _object,
    _optional,
    _utc_timestamp,
)
from chatballs.conversations.inbound_dedup import _already_processed
from chatballs.conversations.models import Message, MessageAuthor
from chatballs.integrations.models import Integration
from chatballs.tenancy.context import TenantContext

RECEIPT_SCHEMA = "chatballs.api-connector.receipt.v1"
STATUSES = frozenset({"PROVIDER_SENT", "DELIVERED", "FAILED"})
RANK = {"QUEUED": 0, "ADAPTER_ACCEPTED": 1, "PROVIDER_SENT": 2, "DELIVERED": 3}
TERMINAL = frozenset({"DELIVERED", "FAILED"})


@dataclass(frozen=True)
class DeliveryReceipt:
    source_id: str
    event_id: str
    command_id: str
    status: str
    provider_message_id: str
    failure_code: str
    fingerprint: str


def parse_delivery_receipt(payload: object) -> DeliveryReceipt:
    body = _object(
        payload,
        {"schema", "source_id", "event", "command_id", "status",
         "provider_message_id", "failure_code"},
        {"schema", "source_id", "event", "command_id", "status"},
    )
    if body["schema"] != RECEIPT_SCHEMA:
        raise ConnectorPayloadError("unsupported_schema", 422)
    source_id = _identifier(body["source_id"], 128)
    event = _object(body["event"], {"id", "occurred_at"}, {"id", "occurred_at"})
    event_id = _identifier(event["id"], 256)
    _utc_timestamp(event["occurred_at"])
    command_id = _identifier(body["command_id"], 36)
    try:
        if str(UUID(command_id)) != command_id:
            raise ValueError("noncanonical")
    except (ValueError, AttributeError) as exc:
        raise ConnectorPayloadError("invalid_payload", 400) from exc
    status = body["status"]
    if status not in STATUSES:
        raise ConnectorPayloadError("unsupported_receipt_status", 422)
    provider_message_id = _optional(body.get("provider_message_id"), 128)
    failure_code = _optional(body.get("failure_code"), 64)
    if failure_code and (not failure_code.isascii()
                         or not all(c.isalnum() or c in "_-." for c in failure_code)):
        raise ConnectorPayloadError("invalid_payload", 400)
    if (status == "FAILED") != bool(failure_code):
        raise ConnectorPayloadError("invalid_payload", 400)
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return DeliveryReceipt(
        source_id=source_id, event_id=event_id, command_id=command_id,
        status=status, provider_message_id=provider_message_id,
        failure_code=failure_code,
        fingerprint=hashlib.sha256(canonical).hexdigest(),
    )


def apply_delivery_receipt(connection: Integration, receipt: DeliveryReceipt) -> None:
    """Call within the ingress tenant transaction, after authentication.

    Unknown commands must be rejected before deduplication, so a too-early
    callback can be retried with the same event ID after command creation.
    """
    if receipt.source_id != f"connection-{connection.pk}":
        raise ConnectorPayloadError("source_mismatch", 409)

    message = (
        Message.objects.select_for_update()
        .filter(
            organization_id=connection.organization_id,
            conversation__connection_id=connection.pk,
            author_type=MessageAuthor.OPERATOR,
            connector_delivery__commandId=receipt.command_id,
        )
        .first()
    )
    if message is None:
        raise ConnectorPayloadError("unknown_command", 409)

    try:
        duplicate = _already_processed(
            TenantContext.for_resource(connection.organization),
            f"api_connector_receipt:{connection.pk}", receipt.event_id, "",
            payload_hash=receipt.fingerprint,
        )
    except ValueError as exc:
        if str(exc) == "connector_event_id_conflict":
            raise ConnectorPayloadError("id_conflict", 409) from exc
        raise
    if duplicate:
        return

    previous = message.connector_delivery
    state = previous.get("state", "QUEUED")
    if state in TERMINAL or (
        receipt.status != "FAILED"
        and RANK.get(receipt.status, -1) <= RANK.get(state, -1)
    ):
        return  # Record the event but never roll the state backwards.

    updated = {
        **previous,
        "state": receipt.status,
        "updatedAt": timezone.now().isoformat(),
    }
    if receipt.provider_message_id:
        updated["providerMessageId"] = receipt.provider_message_id
    if receipt.status == "FAILED":
        # Only a short machine-readable code. Never store provider error text.
        updated["failureCode"] = receipt.failure_code
    message.connector_delivery = updated
    message.save(update_fields=["connector_delivery"])
