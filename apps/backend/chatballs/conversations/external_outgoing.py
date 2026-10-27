"""Native recording of external outgoing messages, without provider-specific code.

Only called after the adapter/Connector authenticated and validated the event.
No provider command is issued; the author's local user ID stays absent.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from chatballs.conversations.domain_events import operation_key, record_queue_entry
from chatballs.conversations.inbound_dedup import _already_processed
from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    ExpectedResponder,
    LifecycleState,
    Message,
    MessageAuthor,
)
from chatballs.conversations.queue import QUEUE_FIELDS, enter_queue
from chatballs.conversations.rules import reply_reminder
from chatballs.integrations.models import Integration
from chatballs.tenancy.context import TenantContext


class ExternalOutgoingConflict(ValueError):
    """A conflict that must abort this domain transaction, retryable as 409."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@transaction.atomic
def record_external_outgoing(
    *, connection: Integration, source: str, event_id: str, fingerprint: str,
    external_chat_id: str, external_message_id: str, text: str,
) -> None:
    """Persist a provider-observed outbound response via native history/rules.

    Caller must have validated and authenticated the external envelope.
    The service is transport-neutral; source is a scoped InboxEvent namespace.
    """

    # Unknown conversations must be retried after real inbound, not created
    # from a forged/unsolicited provider operator event.
    conversation = (
        Conversation.objects.select_for_update()
        .filter(
            organization_id=connection.organization_id,
            connection=integration,
            external_chat_id=external_chat_id,
            lifecycle=LifecycleState.OPEN,
        ).order_by("-last_activity_at", "-pk").first()
    )
    if conversation is None:
        raise ExternalOutgoingConflict("unknown_conversation")

    existing = (
        Message.objects.filter(
            conversation=conversation, external_id=external_message_id,
        ).first()
    )
    if existing and (
        existing.connector_origin != "EXTERNAL_OBSERVED"
        or existing.author_type != MessageAuthor.OPERATOR
        or existing.text != text
    ):
        raise ExternalOutgoingConflict("external_message_id_conflict")

    # If the observed event is actually an echo of our own command, the
    # adapter must send message.echo instead, not duplicate our original.
    if Message.objects.filter(
        conversation=conversation,
        connector_delivery__providerMessageId=external_message_id,
    ).exists():
        raise ExternalOutgoingConflict("echo_expected")

    try:
        duplicate = _already_processed(
            TenantContext.for_resource(connection.organization),
            source, event_id, "",
            payload_hash=fingerprint,
        )
    except ValueError as error:
        if str(error) == "connector_event_id_conflict":
            raise ExternalOutgoingConflict("id_conflict") from error
        raise
    if duplicate or existing:
        return

    Message.objects.create(
        conversation=conversation,
        author_type=MessageAuthor.OPERATOR,
        author_user=None,
        kind="",
        text=text,
        external_id=external_message_id,
        connector_origin="EXTERNAL_OBSERVED",
    )
    conversation.last_activity_at = timezone.now()
    fields = ["last_activity_at"]
    if conversation.control_mode == ControlMode.AI:
        # Pause automatic answers without claiming any internal employee.
        entered = enter_queue(conversation)
        fields.extend(QUEUE_FIELDS)
    else:
        entered = False
        if conversation.control_mode == ControlMode.HUMAN:
            # An external reply did reach the guest; local assignment remains
            # unchanged and no fake public-reply statistic is recorded.
            conversation.expected_responder = ExpectedResponder.CUSTOMER
            fields.append("expected_responder")
    conversation.save(update_fields=fields)
    record_queue_entry(
        conversation, entered=entered,
        operation_id=operation_key(
            source, event_id,
        ),
        actor_kind="SYSTEM", connection=integration,
    )
    if conversation.control_mode == ControlMode.HUMAN:
        reply_reminder.reconcile(conversation)
