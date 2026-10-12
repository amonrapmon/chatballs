"""Durable Gateway AI publication decision.

Queue the revision within the AI result transaction. Later, immediately
before an HTTP dispatch, claim the same row in a short transaction while
holding the Conversation lock. No DB lock may be held during network I/O.

A claimed command may already have crossed the network boundary. Retries
must use the existing command_id even if a native reply arrives later.
"""

from __future__ import annotations

import uuid

from django.db import transaction
from django.utils import timezone

from chatballs.conversations.models import Conversation, DeliveryStatus, Message, MessageAuthor
from chatballs.conversations.realtime import notify_conversation_changed
from chatballs.native_mirror.models import NativeMirrorPublication, PublicationStatus
from chatballs.native_mirror.policy import MirrorMode, mode_for_config
from chatballs.native_mirror.supersession import current_revision
from chatballs.native_mirror.visibility import visible_messages
from chatballs.tenancy.context import TenantContext


class GatewayPublicationError(ValueError):
    """A persisted AI publication has invalid ownership or correlation."""


def queue_ai_publication(*, context: TenantContext, message: Message,
                         revision: int | None) -> None:
    """Add the dispatch guard to a NEW Gateway AI reply in its result commit.

    Caller holds the Conversation lock and has already queued the existing
    Gateway Outbox command in the same transaction.
    """
    connection = message.conversation.connection
    config = connection.config if connection else None
    if mode_for_config(config) != MirrorMode.ENABLED:
        return
    # Old events without snapshots retain legacy handling. They are also
    # terminalized by native mirror acceptance while still PENDING/RUNNING.
    if revision is None:
        return
    if type(revision) is not int or revision < 0:
        raise GatewayPublicationError("Invalid AI mirror revision")
    if (message.author_type != MessageAuthor.AI or message.gateway_command_id is None
            or message.organization_id != context.organization_id):
        raise GatewayPublicationError("AI publication requires an owned Gateway command")
    if current_revision(conversation_id=message.conversation_id) != revision:
        raise GatewayPublicationError("AI publication has a stale revision")
    NativeMirrorPublication.objects.create(
        organization_id=context.organization_id,
        message=message,
        revision=revision,
    )


def claim_ai_publication(*, context: TenantContext, integration_id: int,
                         command: dict) -> bool:
    """True permits (or retries) HTTP delivery, False suppresses before send.

    Caller owns a tenant_atomic() transaction. Untracked legacy/operator
    commands go through unchanged. Existing CLAIMED commands must remain
    retryable despite later native replies or unknown network results.
    """
    raw_id = command.get("command_id")
    try:
        command_id = uuid.UUID(raw_id) if isinstance(raw_id, str) else None
    except (ValueError, AttributeError):
        command_id = None

    if command_id is None:
        # Legacy handler maintains its original validation behavior.
        return True

    conversation_id = (
        NativeMirrorPublication.objects.filter(
            organization_id=context.organization_id,
            message__gateway_command_id=command_id,
        )
        .values_list("message__conversation_id", flat=True)
        .first()
    )
    if conversation_id is None:
        return True

    conversation = (
        Conversation.objects.select_for_update(of=("self",))
        .filter(id=conversation_id, organization_id=context.organization_id)
        .first()
    )
    if conversation is None:
        raise GatewayPublicationError("Publication conversation disappeared")

    publication = (
        NativeMirrorPublication.objects.select_for_update()
        .select_related("message")
        .get(
            organization_id=context.organization_id,
            message__gateway_command_id=command_id,
        )
    )
    message = publication.message
    if (message.conversation_id != conversation.id
            or conversation.connection_id != integration_id
            or message.author_type != MessageAuthor.AI
            or message.gateway_command_id != command_id):
        raise GatewayPublicationError("Gateway publication binding changed")

    recipient = command.get("recipient")
    if (not isinstance(recipient, dict)
            or recipient.get("external_chat_id") != conversation.external_chat_id):
        raise GatewayPublicationError("Gateway publication recipient mismatch")

    if publication.status == PublicationStatus.SUPPRESSED:
        return False
    if publication.status == PublicationStatus.CLAIMED:
        return True
    if publication.status != PublicationStatus.QUEUED:
        raise GatewayPublicationError("Unexpected Gateway publication state")

    if publication.revision != current_revision(conversation_id=conversation.id):
        publication.status = PublicationStatus.SUPPRESSED
        publication.suppressed_at = timezone.now()
        publication.save(update_fields=["status", "suppressed_at"])
        # The only correct public delivery status for a command rejected
        # before claim. Never recycle the original queued timestamp/label.
        message.delivery_status = DeliveryStatus.SUPPRESSED
        message.delivery_status_at = timezone.now()
        message.save(update_fields=["delivery_status", "delivery_status_at"])
        # Inbox ordering must reflect the last VISIBLE message, rather than
        # the AI draft that will never reach the customer.
        last = visible_messages(Message.objects.filter(
            conversation_id=conversation.id,
        )).order_by("-created_at", "-id").values_list("created_at", flat=True).first()
        conversation.last_message_at = last or conversation.created_at
        conversation.save(update_fields=["last_message_at"])
        transaction.on_commit(lambda: notify_conversation_changed(
            conversation.id, organization_id=context.organization_id,
        ))
        return False

    publication.status = PublicationStatus.CLAIMED
    publication.claimed_at = timezone.now()
    publication.save(update_fields=["status", "claimed_at"])
    return True
