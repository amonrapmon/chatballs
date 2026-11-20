"""Record authenticated external outgoing text and supersede earlier AI work."""

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from chatballs.conversations.domain_events import operation_key, record_fact, record_public_reply
from chatballs.conversations.inbound_dedup import _already_processed
from chatballs.conversations.models import (
    ConnectionIdentity,
    Contact,
    ControlMode,
    Conversation,
    ExpectedResponder,
    LifecycleState,
    Message,
    MessageAuthor,
)
from chatballs.conversations.queue import leave_queue
from chatballs.conversations.realtime import notify_conversation_changed
from chatballs.conversations.rules import reply_reminder
from chatballs.integrations.models import Integration
from chatballs.native_mirror.publication import discard_unclaimed_connector_replies
from chatballs.native_mirror.supersession import advance_mirror_revision, lock_conversation_state
from chatballs.tenancy.context import TenantContext


class ExternalOutgoingConflict(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _repeated_event(connection: Integration, source: str, event_id: str, fingerprint: str) -> bool:
    try:
        return _already_processed(
            TenantContext.for_resource(connection.organization), source, event_id, "",
            payload_hash=fingerprint,
        )
    except ValueError as error:
        if str(error) == "connector_event_id_conflict":
            raise ExternalOutgoingConflict("id_conflict") from error
        raise


@transaction.atomic
def record_external_outgoing(
    *, connection: Integration, source: str, event_id: str, fingerprint: str,
    external_chat_id: str, external_message_id: str, text: str,
    occurred_at: datetime, reply_to_message_id: str,
) -> Conversation | None:
    """The authenticated caller must hold the current Integration lock."""
    # Inbound reserves the same InboxEvent namespace before locking a conversation.
    if _repeated_event(connection, source, event_id, fingerprint):
        return None
    routes = Conversation.objects.filter(
        organization_id=connection.organization_id,
        connection=connection,
        external_chat_id=external_chat_id,
    )
    matches = list(routes.select_for_update(of=("self",)).filter(
        lifecycle=LifecycleState.OPEN,
    ).order_by("pk")[:2])
    history = Message.objects.filter(conversation__in=routes)
    if history.filter(connector_delivery__providerMessageId=external_message_id).exists():
        raise ExternalOutgoingConflict("echo_expected")

    existing = history.filter(external_id=external_message_id).order_by("pk").first()
    if existing is not None:
        # Provider identity outlives the particular open conversation.
        if (
            existing.connector_origin != "EXTERNAL_OBSERVED"
            or existing.author_type != MessageAuthor.OPERATOR
            or existing.text != text
            or (existing.external_occurred_at is not None and (
                existing.external_occurred_at != occurred_at
                or existing.external_reply_to_id != reply_to_message_id
            ))
        ):
            raise ExternalOutgoingConflict("external_message_id_conflict")
        return None
    if len(matches) > 1:
        raise ExternalOutgoingConflict("ambiguous_conversation")

    # An outbound-first personal chat has no inbound event to create its
    # contact/route. Only an authenticated, current provider observation may
    # bootstrap it. The outbound actor ID is the *sender account*, not the
    # guest: the private external chat route is the peer identity.
    created = False
    if matches:
        conversation = matches[0]
    else:
        channel = connection.channel
        if channel is None or not channel.is_active:
            raise ExternalOutgoingConflict("unknown_conversation")
        previous = routes.order_by("-created_at", "-pk").first()
        if previous is not None:
            # Preserve the identity for routes that were closed, including
            # routes whose sender ID differs from the chat ID.
            contact = previous.contact
            peer_id = previous.route_external_user_id or external_chat_id
        else:
            peer_id = external_chat_id
            identity = (
                ConnectionIdentity.objects.select_for_update()
                .filter(connection=connection, external_user_id=peer_id)
                .first()
            )
            if identity is None:
                contact = Contact.objects.create(organization_id=connection.organization_id)
                ConnectionIdentity.objects.create(
                    contact=contact, connection=connection, external_user_id=peer_id,
                )
            else:
                contact = identity.contact
        conversation = Conversation.objects.create(
            organization_id=connection.organization_id,
            channel=channel,
            connection=connection,
            contact=contact,
            group=channel.group,
            external_chat_id=external_chat_id,
            route_external_user_id=peer_id,
            control_mode=ControlMode.HUMAN,
            expected_responder=ExpectedResponder.CUSTOMER,
            waiting_since=None,
            previous_conversation=previous,
        )
        created = True
    was_queued = conversation.control_mode == ControlMode.PAUSED or conversation.waiting_since is not None
    state = lock_conversation_state(conversation)
    message = Message.objects.create(
        conversation=conversation,
        author_type=MessageAuthor.OPERATOR,
        text=text,
        external_id=external_message_id,
        external_occurred_at=occurred_at,
        external_reply_to_id=reply_to_message_id,
        connector_origin="EXTERNAL_OBSERVED",
    )
    advance_mirror_revision(state)
    conversation.last_activity_at = timezone.now()
    conversation.last_message_at = conversation.last_activity_at
    # A native operator reply is a human takeover even when the guest wrote
    # first and the conversation was waiting in PAUSED or managed by AI.
    # Do not attribute the reply or acceptance to an unknown Chatballs user.
    conversation.control_mode = ControlMode.HUMAN
    conversation.expected_responder = ExpectedResponder.CUSTOMER
    leave_queue(conversation)
    conversation.save(update_fields=[
        "last_activity_at", "last_message_at", "control_mode",
        "expected_responder", "waiting_since",
    ])
    discard_unclaimed_connector_replies(conversation=conversation)
    # Domain facts, rather than Message alone, power support statistics.
    # A provider-observed human reply has no reliable employee user_id.
    # Record PUBLIC_REPLY before QUEUE_EXITED so the reducer can still
    # calculate the initial response latency from QUEUE_ENTERED.
    operation_id = operation_key("external-native-reply", str(message.pk))
    record_public_reply(message, operation_id=operation_id)
    if was_queued:
        record_fact(
            conversation, "QUEUE_EXITED", operation_id=operation_id,
            actor_kind="SYSTEM",
        )
    reply_reminder.reconcile(conversation)
    # A newly bootstrapped conversation must appear without a manual reload.
    # Publish only after commit so employees never open a rolled-back route.
    transaction.on_commit(
        lambda conversation_id=conversation.pk, organization_id=conversation.organization_id:
            notify_conversation_changed(conversation_id, organization_id=organization_id)
    )
    return conversation if created else None
