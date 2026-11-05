"""Idempotent, identity-scoped profile enrichment without fabricating messages.

Only known ConnectionIdentity rows may be refreshed. A profile observation is
not an explicit contact share, so it cannot mark a phone as verified.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from django.db import transaction

from chatballs.api_connector.payloads import (
    ConnectorPayloadError, _identifier, _object, _optional, _provider_phone,
    _utc_timestamp,
)
from chatballs.conversations.contact_profiles import apply_provider_profile
from chatballs.conversations.inbound_dedup import _already_processed
from chatballs.conversations.models import ConnectionIdentity
from chatballs.tenancy.context import TenantContext


@dataclass(frozen=True)
class ProfileEvent:
    source_id: str
    event_id: str
    fingerprint: str
    external_user_id: str
    display_name: str
    username: str
    provider_phone: str


def parse_profile_event(payload: object) -> ProfileEvent:
    body = _object(payload, {"schema", "source_id", "event", "profile"},
                   {"schema", "source_id", "event", "profile"})
    if body["schema"] != "chatballs.api-connector.event.v1":
        raise ConnectorPayloadError("unsupported_schema", 422)
    source_id = _identifier(body["source_id"], 128)
    event = _object(body["event"], {"id", "type", "occurred_at"},
                    {"id", "type", "occurred_at"})
    event_id = _identifier(event["id"], 256)
    if event["type"] != "contact.profile.updated":
        raise ConnectorPayloadError("unsupported_event_type", 422)
    _utc_timestamp(event["occurred_at"])
    profile = _object(body["profile"],
                      {"external_user_id", "display_name", "username", "phone"},
                      {"external_user_id"})
    external_user_id = _identifier(profile["external_user_id"], 128)
    name = _optional(profile.get("display_name"), 255).strip()
    username = _optional(profile.get("username"), 128).strip()
    phone = _provider_phone(profile.get("phone"))
    if not name and not username and not phone:
        raise ConnectorPayloadError("invalid_payload", 400)
    fingerprint = hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return ProfileEvent(source_id, event_id, fingerprint, external_user_id,
                        name, username, phone)


@transaction.atomic
def apply_profile_event(integration, event: ProfileEvent) -> None:
    if event.source_id != f"connection-{integration.pk}":
        raise ConnectorPayloadError("source_mismatch", 409)
    try:
        duplicate = _already_processed(
            TenantContext.for_resource(integration.organization),
            f"api_connector:{integration.pk}", event.event_id, "",
            payload_hash=event.fingerprint,
        )
    except ValueError as error:
        if str(error) == "connector_event_id_conflict":
            raise ConnectorPayloadError("id_conflict", 409) from error
        raise
    if duplicate:
        return
    identity = (
        ConnectionIdentity.objects.select_for_update().select_related("contact")
        .filter(connection=integration, external_user_id=event.external_user_id)
        .first()
    )
    if identity is None:
        # Contact book entries without a conversation must not create phantom
        # contacts or a route usable for unsolicited messaging.
        return
    apply_provider_profile(
        identity, display_name=event.display_name,
        username=event.username, provider_phone=event.provider_phone,
    )
