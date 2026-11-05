"""One authenticated Connector dispatch seam for supported v1 event families.

Tenant resolution, Bearer validation and request limits live in views.py.
Native ingress, outbound observations and delivery receipts retain their own
business invariants and idempotency. No provider-specific branches exist here.
"""
from __future__ import annotations

from chatballs.api_connector.echo import correlate_connector_echo, parse_connector_echo
from chatballs.api_connector.lifecycle import (
    LIFECYCLE_TYPES,
    LifecycleEvent,
    parse_lifecycle_event,
)
from chatballs.api_connector.observed import ingest_observed_outgoing, parse_observed_outgoing
from chatballs.api_connector.profiles import apply_profile_event, parse_profile_event
from chatballs.api_connector.payloads import (
    ConnectorPayloadError,
    ParsedTextEvent,
    parse_text_event,
)
from chatballs.api_connector.receipts import apply_delivery_receipt, parse_delivery_receipt
from chatballs.conversations.connector_media import apply_media_lifecycle
from chatballs.conversations.ingest import ingest_inbound


def _ingest_message(integration, parsed: ParsedTextEvent) -> str:
    if parsed.source_id != f"connection-{integration.pk}":
        raise ConnectorPayloadError("source_mismatch", 409)
    try:
        ingest_inbound(
            integration, parsed.inbound,
            connector_event_id=parsed.event_id,
            connector_fingerprint=parsed.fingerprint,
        )
    except ValueError as error:
        if str(error) == "connector_event_id_conflict":
            raise ConnectorPayloadError("id_conflict", 409) from error
        raise
    return parsed.event_id


def dispatch_connector_event(
    integration, *, payload: object = None,
    media_event: ParsedTextEvent | LifecycleEvent | None = None,
) -> str:
    """Dispatch a strict JSON envelope or validated multipart native media.

    Caller must hold tenant_atomic after resolving the Integration and checking
    its secret. Return the accepted event ID, not a delivery confirmation.
    """
    if media_event is not None:
        if isinstance(media_event, LifecycleEvent):
            apply_media_lifecycle(integration, media_event)
            return media_event.event_id
        return _ingest_message(integration, media_event)

    if isinstance(payload, dict):
        if payload.get("schema") == "chatballs.api-connector.receipt.v1":
            receipt = parse_delivery_receipt(payload)
            apply_delivery_receipt(integration, receipt)
            return receipt.event_id
        if (payload.get("schema") == "chatballs.api-connector.event.v1"
                and isinstance(payload.get("event"), dict)):
            event_type = payload["event"].get("type")
            if event_type == "contact.profile.updated":
                profile = parse_profile_event(payload)
                apply_profile_event(integration, profile)
                return profile.event_id
            if event_type in LIFECYCLE_TYPES:
                lifecycle = parse_lifecycle_event(payload)
                apply_media_lifecycle(integration, lifecycle)
                return lifecycle.event_id
            if event_type == "message.echo":
                echo = parse_connector_echo(payload)
                correlate_connector_echo(integration, echo)
                return echo.event_id
            if event_type == "message.observed_outgoing":
                observed = parse_observed_outgoing(payload)
                ingest_observed_outgoing(integration, observed)
                return observed.event_id

    return _ingest_message(integration, parse_text_event(payload))
