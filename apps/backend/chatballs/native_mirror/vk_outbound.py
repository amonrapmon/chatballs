"""Durable self-echo identity for sends through the *existing* VK transport.

NativeMirrorReceipt already models terminal SELF_ECHO outcomes, so no extra
table or VK user lookup is needed. This is called after messages.send returns.
"""

from __future__ import annotations

import hashlib

from django.db import IntegrityError, transaction
from django.utils import timezone

from chatballs.integrations.models import IntegrationProvider
from chatballs.native_mirror.models import MirrorReceiptStatus, NativeMirrorReceipt
from chatballs.native_mirror.policy import MirrorMode, mode_for_config
from chatballs.tenancy.database import tenant_atomic


def record_vk_own_send(integration, *, peer_id: str, provider_id: object) -> None:
    """Record an own VK provider message ID before its poll echo can be mirrored.

    Called by the common VK send primitive, covering calls/files as well as
    operator and AI text. The outer caller normally holds its Conversation lock.
    """
    if mode_for_config(integration.config) not in (MirrorMode.SHADOW, MirrorMode.ENABLED):
        return
    if type(provider_id) not in (int, str) or not str(provider_id).isdigit() or int(provider_id) <= 0:
        raise ValueError("VK native mirror cannot correlate messages.send without a message ID")
    source_id = str(integration.config.get("bot_id") or "")
    if not source_id:
        raise ValueError("VK native mirror requires an existing verified community bot_id")
    provider_id = str(provider_id)
    event_key = hashlib.sha256(f"{peer_id}\x00{provider_id}".encode()).hexdigest()
    now = timezone.now()
    with tenant_atomic(integration.organization_id):
        # Two workers may observe the same successful idempotent VK request.
        row = NativeMirrorReceipt.objects.select_for_update().filter(
            integration=integration, external_chat_id=peer_id,
            external_message_id=provider_id,
        ).first()
        if row is not None:
            if row.status != MirrorReceiptStatus.SELF_ECHO:
                raise ValueError("VK outbound conflicts with a previously accepted native reply")
            return
        try:
            with transaction.atomic():
                NativeMirrorReceipt.objects.create(
                    organization_id=integration.organization_id,
                    integration=integration,
                    provider=IntegrationProvider.VK,
                    source_id=source_id,
                    event_id=f"vk-own:{event_key}",
                    external_chat_id=peer_id,
                    external_message_id=provider_id,
                    payload_hash=event_key,
                    occurred_at=now,
                    status=MirrorReceiptStatus.SELF_ECHO,
                    reason="matched_own_outbound",
                    processed_at=now,
                )
        except IntegrityError:
            if not NativeMirrorReceipt.objects.filter(
                integration=integration, external_chat_id=peer_id,
                external_message_id=provider_id, status=MirrorReceiptStatus.SELF_ECHO,
            ).exists():
                raise


def is_vk_own_echo(integration, *, peer_id: str, provider_id: str) -> bool:
    """Read committed send identity; caller should hold Conversation lock."""
    return NativeMirrorReceipt.objects.filter(
        integration=integration,
        provider=IntegrationProvider.VK,
        external_chat_id=peer_id,
        external_message_id=provider_id,
        status=MirrorReceiptStatus.SELF_ECHO,
    ).exists()
