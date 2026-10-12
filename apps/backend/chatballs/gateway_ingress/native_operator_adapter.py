"""Conservative adapter for authenticated TG/MAX Green-API native replies.

Only a first-party gateway can assert provider_event_type, and this adapter
runs *after* the existing bearer + tenant + source validation.
The mapped author is an explicit native bridge service account, not a claim
about which person typed in the messenger application.
"""

from __future__ import annotations

import hashlib
import logging

from chatballs.conversations.models import Message, MessageAuthor
from chatballs.gateway_ingress.payloads import GatewayOperatorMirrorPayload
from chatballs.gateway_ingress.security import GatewayIngressError
from chatballs.identity.models import OrganizationMembership
from chatballs.integrations.models import Integration
from chatballs.native_mirror.classification import (
    VerifiedEvidence, classify_origin,
)
from chatballs.native_mirror.contracts import NativeReplyEvent
from chatballs.native_mirror.policy import MirrorMode
from chatballs.native_mirror.service import NativeMirrorRejected, accept_native_reply
from chatballs.native_mirror.storage import NativeMirrorConflict
from chatballs.tenancy.context import TenantContext

logger = logging.getLogger(__name__)

NATIVE_CLIENT_EVENT = "outgoingMessageReceived"


def _bridge_user_id(context: TenantContext, integration: Integration) -> int:
    configured = integration.config.get("native_operator_user_id")
    if type(configured) is not int or configured <= 0:
        raise GatewayIngressError(409, "Gateway native bridge user is not configured")
    if not OrganizationMembership.objects.filter(
        organization_id=context.organization_id,
        user_id=configured,
        blocked_at__isnull=True,
    ).exists():
        raise GatewayIngressError(409, "Gateway native bridge membership is unavailable")
    return configured


def _correlated_own_message(
    integration: Integration, parsed: GatewayOperatorMirrorPayload,
) -> bool:
    return Message.objects.filter(
        conversation__connection_id=integration.id,
        conversation__external_chat_id=parsed.external_chat_id,
        external_id=parsed.external_message_id,
        gateway_command_id__isnull=False,
        author_type__in=(MessageAuthor.AI, MessageAuthor.OPERATOR),
    ).exists()


def handle_native_operator_mode(
    *, context: TenantContext, integration: Integration,
    parsed: GatewayOperatorMirrorPayload, mode: MirrorMode,
) -> None:
    if mode == MirrorMode.DISABLED:
        return

    # No mutable domain state in SHADOW. The durable raw provider event stays
    # in intercom-gw; this diagnostic log intentionally contains no message
    # text, external IDs or sender names.
    if mode == MirrorMode.SHADOW:
        native_event = parsed.provider_event_type == NATIVE_CLIENT_EVENT
        correlated = _correlated_own_message(integration, parsed)
        logger.info(
            "Native mirror shadow integration=%s native_event=%s own_correlation=%s id_hash=%s",
            integration.id, native_event, correlated,
            hashlib.sha256(parsed.event_id.encode("utf-8")).hexdigest()[:12],
        )
        return

    if mode != MirrorMode.ENABLED:
        raise GatewayIngressError(409, "Unsupported native mirror mode")
    if parsed.provider_event_type != NATIVE_CLIENT_EVENT:
        raise GatewayIngressError(409, "Gateway native origin attestation required")
    if parsed.occurred_at is None:
        raise GatewayIngressError(400, "Gateway native event timestamp required")

    bridge_user_id = _bridge_user_id(context, integration)
    own_correlated = _correlated_own_message(integration, parsed)
    origin = classify_origin(VerifiedEvidence(
        source_authenticated=True,
        own_outbound_correlated=own_correlated,
        staff_membership_verified=not own_correlated,
    ))
    try:
        event = NativeReplyEvent(
            integration_id=integration.id,
            provider=integration.provider,
            source_id=parsed.source_id,
            external_chat_id=parsed.external_chat_id,
            event_id=parsed.event_id,
            external_message_id=parsed.external_message_id,
            occurred_at=parsed.occurred_at,
            text=parsed.text,
            external_reply_to_id=parsed.reply_to_message_id,
        )
        result = accept_native_reply(
            event=event, context=context, origin=origin,
            author_user_id=bridge_user_id if not own_correlated else None,
        )
    except (NativeMirrorRejected, NativeMirrorConflict, ValueError) as error:
        # A failed/contradictory event must not be acknowledged as accepted.
        raise GatewayIngressError(409, str(error)) from error

    # RETRYABLE/UNMATCHED are safely ACKed only because they were committed
    # to the durable receipt with their full payload for later replay.
    logger.info(
        "Native mirror integration=%s outcome=%s retryable=%s",
        integration.id, result.outcome, result.retryable,
    )
