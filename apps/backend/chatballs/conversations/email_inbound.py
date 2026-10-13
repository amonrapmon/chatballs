"""Resolve a web continuation only through a mailbox-scoped mail identifier."""

from django.db import transaction
from django.utils import timezone

from chatballs.conversations.domain_events import operation_key, record_fact, record_queue_entry
from chatballs.conversations.email_facts import record_email_fact
from chatballs.conversations.email_thread_models import EmailThread, EmailThreadMessage
from chatballs.conversations.inbound_dedup import _already_processed
from chatballs.conversations.inbound_media import _store_attachment
from chatballs.conversations.inbound_notifications import notify_inbound
from chatballs.conversations.models import Conversation, Message
from chatballs.conversations.queue import enter_queue
from chatballs.conversations.transports.email_headers import message_ids
from chatballs.tenancy.context import TenantContext


def open_thread(thread, *, operation_id):
    created = False
    conversation = Conversation.objects.select_for_update().get(pk=thread.conversation_id)
    while conversation.lifecycle != "OPEN":
        next_conversation = Conversation.objects.select_for_update().filter(
            organization_id=conversation.organization_id, previous_conversation=conversation,
            channel=conversation.channel, connection=conversation.connection, contact=conversation.contact,
        ).order_by("pk").first()
        if next_conversation is None:
            created = True
            next_conversation = Conversation.objects.create(
                organization=conversation.organization, channel=conversation.channel,
                connection=conversation.connection, contact=conversation.contact,
                group=conversation.group, external_chat_id=conversation.external_chat_id,
                transport_meta=conversation.transport_meta, previous_conversation=conversation,
                control_mode="PAUSED", expected_responder="OPERATOR", waiting_since=timezone.now(),
            )
            record_fact(next_conversation, "FOLLOW_UP", operation_id=operation_id,
                        actor_kind="CONTACT", connection=thread.connection)
            record_queue_entry(next_conversation, entered=True, operation_id=operation_id,
                               actor_kind="CONTACT", connection=thread.connection)
        successor = EmailThread.objects.filter(previous_thread=thread, conversation=next_conversation).first()
        if successor is None:
            successor = EmailThread.objects.create(
                conversation=next_conversation, connection=thread.connection,
                recipient=thread.recipient, subject=thread.subject, previous_thread=thread,
            )
        thread, conversation = successor, next_conversation
    return thread, conversation, created


@transaction.atomic
def ingest_email_continuation(integration, inbound):
    if integration.provider != "EMAIL":
        return False
    meta = inbound.thread_meta or {}
    mail_id = str(meta.get("last_message_id") or inbound.external_id).strip()
    if len(mail_id) > 998:
        mail_id = inbound.external_id
    if EmailThreadMessage.objects.filter(connection=integration, mail_message_id=mail_id).exists():
        return True
    candidates = [*message_ids(meta.get("in_reply_to", "")), *reversed(message_ids(meta.get("references", [])))]
    letters = {letter.mail_message_id: letter for letter in EmailThreadMessage.objects.filter(
        organization_id=integration.organization_id, connection=integration, mail_message_id__in=candidates,
    ).select_related("thread__connection", "thread__conversation")}
    match = next((letters[key] for key in candidates if key in letters), None)
    if match is None or match.thread.recipient != inbound.user_id.strip().lower():
        return False
    context = TenantContext.for_resource(integration.organization)
    if _already_processed(context, f"email:{integration.pk}", inbound.external_id, inbound.text):
        return True
    operation_id = operation_key(f"email:{integration.pk}", inbound.external_id)
    thread, conversation, created = open_thread(match.thread, operation_id=operation_id)
    # Do not feed an EMAIL reply to an autonomous WEB sender. The human mail
    # workflow remains explicit; source WEB and AI configuration are preserved.
    entered = enter_queue(conversation) if conversation.control_mode == "AI" else False
    files_only = bool(inbound.files) and not inbound.text
    message = None
    if not files_only:
        message = Message.objects.create(
            conversation=conversation, author_type="CONTACT", text=inbound.text,
            content_html=inbound.content_html, external_id=inbound.external_id,
        )
    for index, file in enumerate(inbound.files):
        attachment = Message.objects.create(
            conversation=conversation, author_type="CONTACT", kind="file",
            external_id=f"{inbound.external_id}:file:{index}",
        )
        _store_attachment(integration, file, attachment)
        message = message or attachment
    EmailThreadMessage.objects.create(
        thread=thread, connection=integration, message=message, direction="INBOUND", mail_message_id=mail_id,
        in_reply_to=next(iter(message_ids(meta.get("in_reply_to", ""))), ""),
        references=message_ids(meta.get("references", [])),
    )
    conversation.last_activity_at = timezone.now()
    if conversation.control_mode == "HUMAN":
        conversation.expected_responder = "OPERATOR"
    conversation.save(update_fields=["last_activity_at", "control_mode", "expected_responder", "waiting_since"])
    record_queue_entry(conversation, entered=entered, operation_id=operation_id,
                       actor_kind="CONTACT", connection=integration)
    record_email_fact(conversation, integration, actor="CONTACT", operation_id=operation_id)
    notify_inbound(context=context, conversation=conversation, channel=conversation.channel,
                   contact=conversation.contact, integration=integration, inbound=inbound,
                   message_text=inbound.text, is_new=created)
    return True
