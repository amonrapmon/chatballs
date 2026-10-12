"""Transactional acceptance of authenticated native outgoing text replies.

Stage 1 is deliberately not wired into Gateway or VK. Both adapters must
authenticate their transport before passing a normalized event here.
No outgoing send and no AI-turn scheduling happens in this module.
"""

from __future__ import annotations

from django.utils import timezone

from chatballs.conversations.models import Conversation, LifecycleState, Message, MessageAuthor
from chatballs.identity.models import OrganizationMembership
from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.native_mirror.classification import OriginClass
from chatballs.native_mirror.contracts import MirrorOutcome, MirrorResult, NativeReplyEvent
from chatballs.native_mirror.models import (
    MirrorReceiptStatus,
    NativeMirrorConversationState,
)
from chatballs.native_mirror.policy import MirrorMode, mode_for_config
from chatballs.native_mirror.storage import stage_event
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


class NativeMirrorRejected(ValueError):
    """Adapter trust/routing error: do not acknowledge as an accepted event."""


def _integration_for(event: NativeReplyEvent, context: TenantContext) -> Integration:
    integration = Integration.objects.filter(
        id=event.integration_id, organization_id=context.organization_id
    ).first()
    if integration is None or integration.provider != event.provider:
        raise NativeMirrorRejected("Integration/provider does not match tenant event")
    config = integration.config if isinstance(integration.config, dict) else {}
    # Stage 1 supports only explicit source IDs, currently provided by Gateway.
    # VK adapters need their own reviewed source correlation before ENABLED.
    source_id = config.get("source_id")
    if not isinstance(source_id, str) or not source_id or source_id != event.source_id:
        raise NativeMirrorRejected("Native source ID does not match integration")
    return integration


def _member_for(context: TenantContext, author_user_id: int | None) -> int:
    if type(author_user_id) is not int or author_user_id <= 0:
        raise NativeMirrorRejected("Authorized native reply has no verified staff ID")
    if not OrganizationMembership.objects.filter(
        user_id=author_user_id,
        organization_id=context.organization_id,
        blocked_at__isnull=True,
    ).exists():
        raise NativeMirrorRejected("Native author has no active organization membership")
    return author_user_id


def _known_gateway_send(event: NativeReplyEvent, integration: Integration) -> Message | None:
    if integration.provider != IntegrationProvider.GATEWAY:
        return None
    return Message.objects.filter(
        conversation__connection_id=integration.id,
        conversation__external_chat_id=event.external_chat_id,
        external_id=event.external_message_id,
        gateway_command_id__isnull=False,
        author_type__in=(MessageAuthor.AI, MessageAuthor.OPERATOR),
    ).first()


def _complete_without_mirror(receipt, status: str, reason: str,
                             message: Message | None = None) -> MirrorResult:
    receipt.status = status
    receipt.reason = reason
    receipt.pending_text = ""
    receipt.processed_at = timezone.now()
    if message is not None:
        receipt.conversation_id = message.conversation_id
        receipt.message = message
    receipt.save(update_fields=[
        "status", "reason", "pending_text", "processed_at", "conversation", "message"
    ])
    return MirrorResult(
        MirrorOutcome.SELF_ECHO if status == MirrorReceiptStatus.SELF_ECHO
        else MirrorOutcome.UNCLASSIFIED,
        message_id=message.id if message else None,
    )


def _match_conversation(integration: Integration, event: NativeReplyEvent, context):
    # Lock order: Conversation -> NativeMirrorConversationState -> Receipt -> Message.
    return list(
        Conversation.objects.select_for_update(of=("self",))
        .filter(
            organization_id=context.organization_id,
            connection=integration,
            external_chat_id=event.external_chat_id,
            lifecycle=LifecycleState.OPEN,
        )
        .order_by("id")[:2]
    )


def accept_native_reply(
    *, event: NativeReplyEvent, context: TenantContext,
    origin: OriginClass, author_user_id: int | None = None,
) -> MirrorResult:
    """Atomically stage/accept a native reply, leaving control_mode unchanged.

    `origin` and `author_user_id` are trusted adapter facts, never taken
    straight from an unauthenticated provider payload. The service also
    checks integration source and active staff membership inside the tenant.
    Pending receipts keep their text so a retry after restart can process them.
    """
    if not isinstance(event, NativeReplyEvent) or not isinstance(origin, OriginClass):
        raise NativeMirrorRejected("Unvalidated native event or origin")
    with tenant_atomic(context):
        integration = _integration_for(event, context)
        if mode_for_config(integration.config) != MirrorMode.ENABLED:
            return MirrorResult(MirrorOutcome.IGNORED)

        authorized_id = (
            _member_for(context, author_user_id)
            if origin == OriginClass.EXTERNAL_AUTHORIZED else None
        )
        if authorized_id is None and author_user_id is not None:
            raise NativeMirrorRejected("Unclassified/echo event cannot claim a staff author")

        matches = (
            _match_conversation(integration, event, context)
            if origin == OriginClass.EXTERNAL_AUTHORIZED else []
        )
        conversation = matches[0] if len(matches) == 1 else None
        state = None
        if conversation is not None:
            state, _created = NativeMirrorConversationState.objects.select_for_update().get_or_create(
                conversation=conversation,
                defaults={"organization_id":context.organization_id},
            )

        receipt, same_provider_message = stage_event(
            event=event,
            organization_id=context.organization_id,
            author_user_id=authorized_id,
        )
        if same_provider_message or receipt.status != MirrorReceiptStatus.PENDING:
            return MirrorResult(MirrorOutcome.DUPLICATE, message_id=receipt.message_id)

        # The event was first classified as a verified reply. A weaker retry
        # must not erase or consume its pending payload.
        if receipt.author_user_id is not None and authorized_id is None:
            return MirrorResult(MirrorOutcome.RETRYABLE, retryable=True)

        receipt.attempts += 1
        if origin == OriginClass.EXTERNAL_UNCLASSIFIED:
            return _complete_without_mirror(
                receipt, MirrorReceiptStatus.UNCLASSIFIED, "unverified_origin"
            )

        own_send = _known_gateway_send(event, integration)
        if own_send is not None:
            return _complete_without_mirror(
                receipt, MirrorReceiptStatus.SELF_ECHO, "matched_own_outbound", own_send
            )
        if origin == OriginClass.SELF_ECHO:
            # No verified provider correlation => do not silently claim own echo.
            return _complete_without_mirror(
                receipt, MirrorReceiptStatus.UNCLASSIFIED, "uncorrelated_own_echo"
            )

        if conversation is None:
            receipt.reason = (
                "conversation_missing" if not matches else "conversation_ambiguous"
            )
            receipt.save(update_fields=["attempts", "reason"])
            return MirrorResult(
                MirrorOutcome.RETRYABLE if not matches else MirrorOutcome.UNMATCHED,
                retryable=True,
            )

        message = Message.objects.create(
            conversation=conversation,
            author_type=MessageAuthor.OPERATOR,
            author_user_id=authorized_id,
            text=receipt.pending_text,
            external_id=event.external_message_id,
            external_occurred_at=event.occurred_at,
            external_reply_to_id=event.external_reply_to_id,
        )
        state.revision += 1
        state.save(update_fields=["revision", "updated_at"])
        conversation.last_activity_at = timezone.now()
        conversation.save(update_fields=["last_activity_at"])

        receipt.message = message
        receipt.conversation = conversation
        receipt.pending_text = ""
        receipt.status = MirrorReceiptStatus.STORED
        receipt.reason = ""
        receipt.processed_at = timezone.now()
        receipt.save(update_fields=[
            "message", "conversation", "pending_text", "status", "reason",
            "attempts", "processed_at",
        ])
        return MirrorResult(MirrorOutcome.STORED, message_id=message.id)
