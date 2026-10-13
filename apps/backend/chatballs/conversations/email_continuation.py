"""Atomic public mail operation and explicit retries of its immutable route."""

from email.utils import make_msgid

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from chatballs.conversations.access import require_conversation_action
from chatballs.conversations.domain_events import is_accepted, operation_key
from chatballs.conversations.reply_access import require_human_reply
from chatballs.conversations.email_attempt_models import EmailSendAttempt, EmailSendOperation
from chatballs.conversations.email_attachment import attachment_matches, read_attachment, store_attachment
from chatballs.conversations.email_facts import record_email_fact
from chatballs.conversations.email_options import letter_mailbox_available, mailbox_available, saved_addresses
from chatballs.conversations.email_thread_models import EmailThread, EmailThreadMessage
from chatballs.conversations.models import Conversation, Message
from chatballs.conversations.services import ClaimError, claim_locked_conversation
from chatballs.events.services import DomainEvent, enqueue_event
from chatballs.i18n import customer_language, t
from chatballs.identity.models import Organization
from chatballs.identity.policy import can_administer_access
from chatballs.integrations.models import Integration
from chatballs.tenancy.context import TenantContext

EMAIL_SEND_REQUESTED = "conversations.email_send_requested"


def conflict(key):
    raise ClaimError(t(f"conversations.email_{key}"))


def require_reply(context, conversation, *, claim=False, allow_unclaimed=False):
    require_conversation_action(context, conversation, "conversations.operate")
    if conversation.archived_at and not can_administer_access(context.membership):
        raise Conversation.DoesNotExist
    require_human_reply(context=context, conversation=conversation, allow_unclaimed=claim or allow_unclaimed)
    if claim and (conversation.control_mode != "HUMAN" or (
        conversation.assigned_operator_id == context.actor_user.pk and not is_accepted(conversation)
    )):
        return claim_locked_conversation(context=context, conversation=conversation)
    return conversation


def create_attempt(context, operation):
    number = (operation.attempts.order_by("-number").values_list("number", flat=True).first() or 0) + 1
    # Resource context lets the handler record a safe failure even if the human
    # loses membership before dispatch. It rechecks that human's current rights.
    event = enqueue_event(DomainEvent(
        aggregate_type="email_operation", aggregate_id=str(operation.pk),
        event_type=EMAIL_SEND_REQUESTED,
        payload={"operation_id": operation.pk, "attempt": number},
        tenant_context=TenantContext.for_resource(context.organization),
    ))
    return EmailSendAttempt.objects.create(
        operation=operation, number=number, initiated_by=context.membership, outbox_event=event,
    )


@transaction.atomic
def send_email_reply(*, context, conversation_id, recipient, connection_id, text, client_key, subject="", upload=None):
    # Also serialize a client key used concurrently for different conversations.
    Organization.objects.select_for_update().get(pk=context.organization_id)
    conversation = Conversation.objects.select_for_update().get(
        pk=conversation_id, organization_id=context.organization_id,
    )
    require_conversation_action(context, conversation, "conversations.operate")
    if conversation.archived_at and not can_administer_access(context.membership):
        raise Conversation.DoesNotExist
    recipient, text, client_key, subject = (value.strip() for value in (recipient, text, client_key, subject))
    recipient = recipient.lower()
    subject = subject or t("conversations.email_default_subject", language=customer_language(context.organization))
    attachment = read_attachment(upload)
    if (not text and attachment is None) or len(text) > 20000 or not client_key or len(client_key) > 128 or len(subject) > 998 or any(c in subject for c in "\r\n"):
        raise ValidationError({"detail": t("conversations.email_invalid_request")})
    existing = EmailSendOperation.objects.select_related("letter__thread", "letter__message").filter(
        organization_id=context.organization_id, client_key=client_key,
    ).first()
    if existing:
        thread = existing.letter.thread
        if (thread.conversation_id, thread.recipient, thread.connection_id, thread.subject, existing.letter.message.text) != (
            conversation.pk, recipient, connection_id, subject, text,
        ) or not attachment_matches(existing.letter.message, attachment):
            conflict("key_conflict")
        return existing, False
    if not conversation.connection_id or conversation.connection.provider != "WEB":
        conflict("web_required")
    if recipient not in saved_addresses(conversation):
        conflict("address_unavailable")
    connection = Integration.objects.select_related("channel").filter(
        pk=connection_id, organization_id=context.organization_id,
    ).first()
    if connection is None or not mailbox_available(connection):
        conflict("connection_unavailable")
    conversation = require_reply(context, conversation, claim=True)
    thread = EmailThread.objects.filter(
        conversation=conversation, connection=connection, recipient=recipient, subject=subject,
    ).order_by("-pk").first()
    if thread is None:
        thread = EmailThread.objects.create(
            conversation=conversation, connection=connection, recipient=recipient, subject=subject,
        )
    previous = thread.letters.order_by("-pk").first()
    message = Message.objects.create(
        conversation=conversation, author_type="OPERATOR", author_user=context.actor_user, text=text,
    )
    store_attachment(message, attachment)
    letter = EmailThreadMessage.objects.create(
        thread=thread, connection=connection, message=message, direction="OUTBOUND",
        mail_message_id=make_msgid(domain=connection.config["email"].rsplit("@", 1)[-1]),
        in_reply_to=previous.mail_message_id if previous else "",
        references=[*previous.references, previous.mail_message_id][-30:] if previous else [],
        sender_address=connection.config["email"].strip().lower(), recipient_address=recipient,
        subject=subject, mailbox_name=connection.name,
    )
    operation = EmailSendOperation.objects.create(
        letter=letter, initiated_by=context.membership, client_key=client_key,
    )
    create_attempt(context, operation)
    conversation.last_activity_at = timezone.now()
    conversation.expected_responder = "CUSTOMER"
    conversation.save(update_fields=["last_activity_at", "expected_responder"])
    record_email_fact(conversation, connection, actor="HUMAN", user_id=context.actor_user.pk,
                      operation_id=operation_key("email-reply", message.pk))
    return operation, True


def retry_allowed(operation):
    states = list(operation.attempts.values_list("state", flat=True))
    return bool(states and all(state in {"FAILED", "UNKNOWN"} for state in states))


@transaction.atomic
def retry_email_reply(*, context, conversation_id, operation_id, acknowledge_unknown=False):
    conversation = Conversation.objects.select_for_update().get(
        pk=conversation_id, organization_id=context.organization_id,
    )
    require_reply(context, conversation)
    operation = EmailSendOperation.objects.select_for_update().select_related("letter__connection").get(
        pk=operation_id, organization_id=context.organization_id, letter__thread__conversation=conversation,
    )
    if not retry_allowed(operation):
        conflict("retry_unavailable")
    if operation.attempts.filter(state="UNKNOWN").exists() and not acknowledge_unknown:
        conflict("unknown_ack_required")
    if not letter_mailbox_available(operation.letter):
        conflict("connection_unavailable")
    return create_attempt(context, operation)
