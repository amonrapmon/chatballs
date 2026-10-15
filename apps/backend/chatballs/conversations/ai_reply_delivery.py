"""Persist the actual route; retries only deliver the already stored reply."""

from email.utils import make_msgid

from chatballs.conversations import transports
from chatballs.conversations.domain_events import operation_key, record_public_reply
from chatballs.conversations.email_facts import record_email_fact
from chatballs.conversations.email_thread_models import EmailThreadMessage
from chatballs.conversations.models import Message
from chatballs.conversations.transports.email import prepare_text
from chatballs.conversations.transports.email_smtp import continuation_message, deliver_message
from chatballs.integrations.models import Integration
from chatballs.tenancy.database import tenant_atomic


class AiDeliveryFailed(Exception):
    pass


def reply_route(turn):
    letter = getattr(turn.message, "email_transport", None)
    if letter is not None:
        return {"connectionId": letter.connection_id, "chatId": letter.thread.recipient,
                "userId": turn.user_id, "representation": "text", "sourceLetterId": letter.pk}
    connection = turn.conversation.connection
    route = {"connectionId": connection.pk if connection else None,
            "chatId": turn.conversation.external_chat_id, "userId": turn.user_id,
            "representation": "html" if connection and connection.provider == "WEB" else "text"}
    if connection and connection.provider == "EMAIL":
        route["mailMeta"] = {key: turn.conversation.transport_meta.get(key, "") for key in ("subject", "last_message_id")}
        route["messageId"] = make_msgid()
    return route


def bind_reply(turn, message, route):
    message.ai_reply_to = turn.message
    message.ai_delivery = route
    message.save(update_fields=["ai_reply_to", "ai_delivery"])
    if route.get("sourceLetterId"):
        source = EmailThreadMessage.objects.select_related("connection", "thread").get(pk=route["sourceLetterId"])
        EmailThreadMessage.objects.create(
            thread=source.thread, connection=source.connection, message=message, direction="OUTBOUND",
            mail_message_id=make_msgid(), in_reply_to=source.mail_message_id,
            references=[*source.references, source.mail_message_id][-30:],
            sender_address=source.recipient_address, recipient_address=source.sender_address or source.thread.recipient,
            subject=source.subject or source.thread.subject, mailbox_name=source.mailbox_name,
        )


def record_reply(message):
    letter = getattr(message, "email_transport", None)
    if letter:
        return record_email_fact(message.conversation, letter.connection, actor="AI",
                                 operation_id=operation_key("reply", message.pk))
    return record_public_reply(message)


def deliver_saved(source_id, context):
    with tenant_atomic(context):
        message = Message.objects.select_for_update().filter(
            ai_reply_to_id=source_id, organization_id=context.organization_id,
        ).first()
        if message is None or message.ai_delivery.get("sent") or not message.text:
            return
        route = message.ai_delivery
        connection = Integration.objects.select_related("organization").filter(pk=route.get("connectionId")).first()
        if connection is None:
            return
        letter = getattr(message, "email_transport", None)
        outgoing = continuation_message(letter) if letter else None
        if outgoing is None and connection.provider == "EMAIL":
            outgoing = prepare_text(connection, target=route["chatId"], text=message.text, meta=route.get("mailMeta", {}))
            outgoing["Message-ID"] = route["messageId"]
    if outgoing is not None:
        accepted = deliver_message(connection, outgoing).state == "SMTP_ACCEPTED"
    else:
        accepted = transports.send_reply(connection, chat_id=route["chatId"], user_id=route["userId"], text=message.text)
    if not accepted:
        raise AiDeliveryFailed("AI reply transport rejected delivery")
    with tenant_atomic(context):
        Message.objects.filter(pk=message.pk).update(ai_delivery={**route, "sent": True})
