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
from chatballs.identity.models import OrganizationStatus
from chatballs.identity.operation_modes import OperationMode, autonomous_allowed, lock_organization
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

    Caller owns a tenant_atomic() transaction. A known AI command is checked
    even when it predates publication rows. Existing CLAIMED commands remain
    retryable because they may already have crossed the network boundary.
    """
    raw_id = command.get("command_id")
    try:
        command_id = uuid.UUID(raw_id) if isinstance(raw_id, str) else None
    except (ValueError, AttributeError):
        command_id = None

    if command_id is None:
        # Legacy handler maintains its original validation behavior.
        return True

    # All first-send decisions serialize with organization mode changes. Then
    # lock Conversation -> Message -> Publication, matching reply/takeover paths.
    organization = lock_organization(context.organization_id)
    candidate = Message.objects.filter(
        organization_id=context.organization_id,
        gateway_command_id=command_id,
    ).values_list("id", "conversation_id").first()
    if candidate is None:
        # Keep the existing handler path for old uncorrelated Gateway commands.
        return True
    message_id, conversation_id = candidate

    conversation = (
        Conversation.objects.select_for_update(of=("self",)).select_related(
            "connection", "channel__ai_agent__provider_integration",
            "channel__provider_integration",
        )
        .filter(id=conversation_id, organization_id=context.organization_id)
        .first()
    )
    if conversation is None:
        raise GatewayPublicationError("Publication conversation disappeared")

    message = (
        Message.objects.select_for_update(of=("self",))
        .filter(id=message_id, organization_id=context.organization_id)
        .first()
    )
    if message is None or message.conversation_id != conversation.id:
        raise GatewayPublicationError("Gateway command message binding changed")
    if conversation.connection_id != integration_id or message.gateway_command_id != command_id:
        raise GatewayPublicationError("Gateway publication binding changed")

    recipient = command.get("recipient")
    if (not isinstance(recipient, dict)
            or recipient.get("external_chat_id") != conversation.external_chat_id):
        raise GatewayPublicationError("Gateway command recipient mismatch")

    publication = NativeMirrorPublication.objects.select_for_update().filter(
        organization_id=context.organization_id, message_id=message.id,
    ).first()
    if message.author_type == MessageAuthor.OPERATOR:
        if publication is not None:
            raise GatewayPublicationError("Operator command has an AI publication row")
        return True
    if message.author_type != MessageAuthor.AI:
        raise GatewayPublicationError("Gateway command is not a public reply")

    if publication is not None and publication.status == PublicationStatus.SUPPRESSED:
        return False
    if publication is not None and publication.status == PublicationStatus.CLAIMED:
        return True
    if publication is not None and publication.status != PublicationStatus.QUEUED:
        raise GatewayPublicationError("Unexpected Gateway publication state")

    route = message.ai_delivery if isinstance(message.ai_delivery, dict) else {}
    expected_revision = (
        publication.revision if publication is not None
        else route.get("mirrorRevision", 0)
    )
    revision_valid = type(expected_revision) is int and expected_revision >= 0
    current = (
        revision_valid
        and current_revision(conversation_id=conversation.id) == expected_revision
    )
    eligible = (
        message.delivery_status != DeliveryStatus.SUPPRESSED
        and route.get("cancelled") is not True
        and type(route.get("modeVersion", 1)) is int
        and route.get("modeVersion", 1) == organization.operation_mode_version
        and organization.status == OrganizationStatus.ACTIVE
        and organization.operation_mode == OperationMode.AI_AGENTS
        and conversation.lifecycle == "OPEN"
        and conversation.control_mode == "AI"
        and conversation.assigned_operator_id is None
        and current
        and autonomous_allowed(
            conversation.channel, organization=organization,
            connection=conversation.connection, conversation=conversation,
        )
    )
    if not eligible:
        now = timezone.now()
        if publication is not None:
            publication.status = PublicationStatus.SUPPRESSED
            publication.suppressed_at = now
            publication.save(update_fields=["status", "suppressed_at"])
        else:
            NativeMirrorPublication.objects.create(
                organization_id=context.organization_id,
                message=message,
                revision=expected_revision if revision_valid else 0,
                status=PublicationStatus.SUPPRESSED,
                suppressed_at=now,
            )
        # The only correct public delivery status for a command rejected
        # before claim. Never recycle the original queued timestamp/label.
        message.delivery_status = DeliveryStatus.SUPPRESSED
        message.delivery_status_at = now
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

    claimed_at = timezone.now()
    if publication is not None:
        publication.status = PublicationStatus.CLAIMED
        publication.claimed_at = claimed_at
        publication.save(update_fields=["status", "claimed_at"])
    else:
        # Legacy AI commands acquire the same durable retry boundary on first
        # claim, after passing the current autonomy and revision guards.
        NativeMirrorPublication.objects.create(
            organization_id=context.organization_id,
            message=message,
            revision=expected_revision,
            status=PublicationStatus.CLAIMED,
            claimed_at=claimed_at,
        )
    return True
