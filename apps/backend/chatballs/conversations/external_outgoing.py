"""Record authenticated external outgoing text and supersede earlier AI work."""

from datetime import datetime

from django.db import transaction
from django.utils import timezone

from chatballs.conversations.inbound_dedup import _already_processed
from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    ExpectedResponder,
    LifecycleState,
    Message,
    MessageAuthor,
)
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
) -> None:
    """The authenticated caller must hold the current Integration lock."""
    # Inbound reserves the same InboxEvent namespace before locking a conversation.
    if _repeated_event(connection, source, event_id, fingerprint):
        return
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
        return
    if len(matches) != 1:
        raise ExternalOutgoingConflict("ambiguous_conversation" if matches else "unknown_conversation")

    conversation = matches[0]
    state = lock_conversation_state(conversation)
    Message.objects.create(
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
    fields = ["last_activity_at"]
    if conversation.control_mode == ControlMode.HUMAN:
        conversation.expected_responder = ExpectedResponder.CUSTOMER
        fields.append("expected_responder")
    conversation.save(update_fields=fields)
    discard_unclaimed_connector_replies(conversation=conversation)
    if conversation.control_mode == ControlMode.HUMAN:
        reply_reminder.reconcile(conversation)
