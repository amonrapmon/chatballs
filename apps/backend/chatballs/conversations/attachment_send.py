"""The existing employee attachment command, shared with native actions."""

from django.core.files.base import ContentFile
from django.utils import timezone

from chatballs.api_connector.outbound import outbound_available, queue_operator_file
from chatballs.conversations import transports
from chatballs.conversations.attachment_policy import validate_upload
from chatballs.conversations.media_operations import media_operation
from chatballs.conversations.models import (
    ConnectionIdentity,
    ExpectedResponder,
    LifecycleState,
    Message,
    MessageAuthor,
    MessageKind,
)
from chatballs.conversations.reply_audit import audit_reply
from chatballs.conversations.reply_claim_service import claim_reply
from chatballs.conversations.reply_problems import ReplyProblem, problem
from chatballs.conversations.template_send_guard import (
    UnfilledTemplateVariables,
    require_filled_text,
)
from chatballs.conversations.transports.base import guess_content_type, safe_filename
from chatballs.integrations.models import IntegrationProvider


@media_operation(MessageKind.FILE)
def send_attachment_reply(*, context, conversation, upload, text="", operation_id=None, request=None):
    if conversation.lifecycle != LifecycleState.OPEN:
        return problem("conversations.closed", 409)
    connection = conversation.connection
    is_connector = connection is not None and connection.provider == IntegrationProvider.API_CONNECTOR
    if is_connector:
        if (connection.config.get("connectorMediaOutboundEnabled") is not True
                or not outbound_available(connection)):
            return problem("conversations.files_unavailable_channel")
    elif connection is None or not transports.supports_file_send(connection):
        return problem("conversations.files_unavailable_channel")
    if upload is None:
        return problem("conversations.attach_file")
    invalid = validate_upload(upload)
    if invalid:
        return ReplyProblem({"detail": invalid}, 400)
    name = safe_filename(upload.name or "")
    content_type = (upload.content_type or "").split(";")[0] or guess_content_type(name)
    caption = str(text).strip()[:4000]
    try:
        require_filled_text(caption)
    except UnfilledTemplateVariables as error:
        return ReplyProblem(error.payload(), 400)
    content = upload.read()
    if is_connector:
        if len(caption) > 1024:
            return problem("conversations.connector_caption_too_long")
        signatures = {
            "image/jpeg": ((".jpg", ".jpeg"), b"\xff\xd8\xff"),
            "image/png": ((".png",), b"\x89PNG\r\n\x1a\n"),
            "application/pdf": ((".pdf",), b"%PDF-"),
        }
        item = signatures.get(content_type)
        if not item or not name.lower().endswith(item[0]) or not content.startswith(item[1]):
            return problem("conversations.files_unavailable_channel")
    conversation = claim_reply(context=context, conversation_id=conversation.pk,
        operation_id=operation_id, request=request)
    identity = ConnectionIdentity.objects.filter(connection=connection, contact=conversation.contact).first()
    if not is_connector and not transports.send_file(connection, chat_id=conversation.external_chat_id,
            user_id=identity.external_user_id if identity else "", content=content,
            filename=name, content_type=content_type, caption=caption):
        return problem("conversations.file_send_failed", 502)
    message = Message.objects.create(conversation=conversation, author_type=MessageAuthor.OPERATOR,
        author_user=context.actor_user, kind=MessageKind.FILE, text=caption,
        attachment_name=name, attachment_content_type=content_type, attachment_size=len(content))
    message.attachment.save(name, ContentFile(content), save=False)
    message.save(update_fields=["attachment"])
    if is_connector:
        queue_operator_file(context=context, conversation=conversation, message=message, content=content)
    conversation.last_activity_at = timezone.now()
    conversation.expected_responder = ExpectedResponder.CUSTOMER
    conversation.save(update_fields=["last_activity_at", "expected_responder"])
    audit_reply(context, "file_queued" if is_connector else "file_sent", conversation, request=request)
    return message
