"""Durable AI publication decision for command transports.

Queue the revision within the AI result transaction. Later, immediately
before an HTTP dispatch, claim the same row in a short transaction while
holding the Conversation lock. No DB lock may be held during network I/O.

A claimed command may already have crossed the network boundary. Retries
must use the existing command_id even if a native reply arrives later.
"""

from __future__ import annotations

import uuid

from django.utils import timezone

from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    DeliveryStatus,
    ExpectedResponder,
    Message,
    MessageAuthor,
)
from chatballs.identity.models import OrganizationStatus
from chatballs.identity.operation_modes import OperationMode, autonomous_allowed, lock_organization
from chatballs.integrations.models import IntegrationProvider
from chatballs.native_mirror.models import NativeMirrorPublication, PublicationStatus
from chatballs.native_mirror.policy import MirrorMode, mode_for_config
from chatballs.native_mirror.supersession import current_revision
from chatballs.native_mirror.visibility import visible_messages
from chatballs.tenancy.context import TenantContext


class GatewayPublicationError(ValueError):
    """A persisted AI publication has invalid ownership or correlation."""


def queue_ai_publication(*, context: TenantContext, message: Message,
                         revision: int | None) -> None:
    """Add the dispatch guard to a new AI reply in its result commit.

    Caller holds the Conversation lock and has already queued the existing
    Outbox command in the same transaction.
    """
    connection = message.conversation.connection
    is_connector = connection is not None and connection.provider == IntegrationProvider.API_CONNECTOR
    if not is_connector and mode_for_config(connection.config if connection else None) != MirrorMode.ENABLED:
        return
    # Old events without snapshots retain legacy handling. They are also
    # terminalized by native mirror acceptance while still PENDING/RUNNING.
    if revision is None and not is_connector:
        return
    if type(revision) is not int or revision < 0:
        raise GatewayPublicationError("Invalid AI mirror revision")
    command_id = message.connector_delivery.get("commandId") if is_connector else message.gateway_command_id
    if (message.author_type != MessageAuthor.AI or not command_id
            or message.organization_id != context.organization_id):
        raise GatewayPublicationError("AI publication requires an owned command")
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

    if message.author_type == MessageAuthor.OPERATOR:
        if _locked_publication(message) is not None:
            raise GatewayPublicationError("Operator command has an AI publication row")
        return True
    if message.author_type != MessageAuthor.AI:
        raise GatewayPublicationError("Gateway command is not a public reply")
    return claim_locked_ai_publication(organization, conversation, message)


def _locked_publication(message):
    return NativeMirrorPublication.objects.select_for_update().filter(
        organization_id=message.organization_id, message_id=message.pk,
    ).first()


def _suppress_message(message, publication, revision, now):
    if publication is not None:
        publication.status = PublicationStatus.SUPPRESSED
        publication.suppressed_at = now
        publication.save(update_fields=["status", "suppressed_at"])
    else:
        NativeMirrorPublication.objects.create(
            organization_id=message.organization_id,
            message=message, revision=revision,
            status=PublicationStatus.SUPPRESSED, suppressed_at=now,
        )
    message.delivery_status = DeliveryStatus.SUPPRESSED
    message.delivery_status_at = now
    fields = ["delivery_status", "delivery_status_at"]
    if message.connector_delivery:
        message.connector_delivery = {**message.connector_delivery, "state": "SUPPRESSED"}
        fields.append("connector_delivery")
    message.save(update_fields=fields)


def _refresh_visible_activity(conversation):
    last = visible_messages(Message.objects.filter(
        conversation_id=conversation.id,
    )).order_by("-created_at", "-id").values_list("created_at", flat=True).first()
    conversation.last_message_at = last or conversation.created_at
    conversation.save(update_fields=["last_message_at"])


def discard_unclaimed_connector_replies(*, conversation: Conversation) -> None:
    """Hide superseded Connector drafts while the mirror holds Conversation."""
    messages = list(Message.objects.select_for_update(of=("self",)).filter(
        conversation=conversation, author_type=MessageAuthor.AI,
        connector_delivery__state="QUEUED",
        native_mirror_publication__status=PublicationStatus.QUEUED,
    ).order_by("pk"))
    if messages:
        now = timezone.now()
        for message in messages:
            publication = _locked_publication(message)
            _suppress_message(message, publication, publication.revision, now)
        _refresh_visible_activity(conversation)


def claim_locked_ai_publication(
    organization, conversation, message, *, authorize=None, allow_own_pause=False,
) -> bool:
    """Claim under Organization -> Conversation -> Message locks."""
    publication = _locked_publication(message)
    if publication is None and message.connector_delivery:
        raise GatewayPublicationError("Connector AI command has no publication row")

    if publication is not None and publication.status == PublicationStatus.SUPPRESSED:
        return False
    if publication is not None and publication.status == PublicationStatus.CLAIMED:
        return True
    if publication is not None and publication.status != PublicationStatus.QUEUED:
        raise GatewayPublicationError("Unexpected AI publication state")

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
    own_pause = (
        allow_own_pause and route.get("pausedByTurn") is True and message.ai_reply_to_id is not None
        and conversation.control_mode == ControlMode.PAUSED
        and conversation.expected_responder == ExpectedResponder.OPERATOR
        and conversation.waiting_since is not None
    )
    eligible = (
        message.delivery_status != DeliveryStatus.SUPPRESSED
        and route.get("cancelled") is not True
        and type(route.get("modeVersion", 1)) is int
        and route.get("modeVersion", 1) == organization.operation_mode_version
        and organization.status == OrganizationStatus.ACTIVE
        and organization.operation_mode == OperationMode.AI_AGENTS
        and conversation.lifecycle == "OPEN"
        and (conversation.control_mode == ControlMode.AI or own_pause)
        and conversation.assigned_operator_id is None
        and current
        and autonomous_allowed(
            conversation.channel, organization=organization,
            connection=conversation.connection, conversation=None if own_pause else conversation,
        )
        and (authorize is None or authorize())
    )
    if not eligible:
        _suppress_message(message, publication, expected_revision if revision_valid else 0, timezone.now())
        _refresh_visible_activity(conversation)
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
            organization_id=message.organization_id,
            message=message,
            revision=expected_revision,
            status=PublicationStatus.CLAIMED,
            claimed_at=claimed_at,
        )
    if message.connector_delivery:
        from chatballs.conversations.domain_events import record_public_reply

        message.conversation = conversation
        record_public_reply(message)
    return True
