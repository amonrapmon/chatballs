"""Файлы и фото в диалоге (дизайн-базлайн v2, композер «Прикрепить»).

Приём входящих — в ingest; здесь HTTP-слой оператора: отдача вложения и
отправка файла в диалог (Telegram, MAX, почта, Web). Правила те же, что у
текстового ответа: отправка перехватывает диалог у AI/очереди на себя.
"""

from __future__ import annotations

from django.core.files.base import ContentFile
from django.http import FileResponse
from django.utils import timezone
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response

from chatballs.api_connector.outbound import outbound_available, queue_operator_file
from chatballs.conversations import transports
from chatballs.conversations.attachment_policy import MAX_FILE_BYTES as MAX_FILE_BYTES
from chatballs.conversations.attachment_policy import validate_upload as validate_upload
from chatballs.conversations.media_operations import public_media_operation
from chatballs.conversations.models import (
    ConnectionIdentity,
    Conversation,
    ExpectedResponder,
    LifecycleState,
    Message,
    MessageAuthor,
    MessageKind,
)
from chatballs.conversations.serializers import message_payload
from chatballs.conversations.template_send_guard import (
    UnfilledTemplateVariables,
    require_filled_text,
)
from chatballs.conversations.transports.base import guess_content_type, safe_filename
from chatballs.conversations.view_base import ConversationViewBase
from chatballs.conversations.voice_views import _visible_message
from chatballs.i18n import t
from chatballs.integrations.models import IntegrationProvider

INLINE_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp", "application/pdf")


def attachment_response(message: Message, *, inline: bool = False) -> FileResponse:
    content_type = message.attachment_content_type or guess_content_type(message.attachment_name)
    return FileResponse(
        message.attachment.open("rb"),
        content_type=content_type,
        as_attachment=not (inline and content_type in INLINE_TYPES),
        filename=message.attachment_name or "file",
    )


class MessageAttachmentView(ConversationViewBase):
    def get(self, request: Request, message_id: int) -> Response:
        try:
            message = _visible_message(request, message_id)
        except (Message.DoesNotExist, Conversation.DoesNotExist):
            return Response({"detail": t("conversations.message_not_found")}, status=404)
        if message.kind != MessageKind.FILE or not message.attachment:
            return Response({"detail": t("conversations.file_unavailable")}, status=404)
        return attachment_response(message, inline="inline" in request.GET)


class ConversationAttachmentView(ConversationViewBase):
    """Отправка файла оператором: multipart `file` + необязательная подпись `text`."""

    public_reply_kind = MessageKind.FILE
    required_capability = "conversations.operate"
    parser_classes = [MultiPartParser, FormParser]

    @public_media_operation
    def post(self, request: Request, conversation_id: int) -> Response:
        from chatballs.conversations.views import claim_for_reply

        try:
            conversation = self._conversation(request, conversation_id, self.required_capability)
        except Conversation.DoesNotExist:
            return Response({"detail": t("conversations.not_found")}, status=404)
        if conversation.lifecycle != LifecycleState.OPEN:
            return Response({"detail": t("conversations.closed")}, status=409)
        connection = conversation.connection
        is_connector = connection is not None and connection.provider == IntegrationProvider.API_CONNECTOR
        if is_connector:
            if (connection.config.get("connectorMediaOutboundEnabled") is not True
                    or not outbound_available(connection)):
                return Response({"detail": t("conversations.files_unavailable_channel")}, status=400)
        elif connection is None or not transports.supports_file_send(connection):
            return Response({"detail": t("conversations.files_unavailable_channel")}, status=400)
        upload = request.FILES.get("file")
        if upload is None:
            return Response({"detail": t("conversations.attach_file")}, status=400)
        problem = validate_upload(upload)
        if problem:
            return Response({"detail": problem}, status=400)
        name = safe_filename(upload.name or "")
        content_type = (upload.content_type or "").split(";")[0] or guess_content_type(name)
        caption = str(request.data.get("text", "")).strip()[:4000]
        try:
            require_filled_text(caption)
        except UnfilledTemplateVariables as error:
            return Response(error.payload(), status=400)

        # The Telegram upload caption limit is 1024. Reject before a native
        # message/Outbox is created instead of accepting a command the adapter
        # can never deliver.
        if is_connector and len(caption) > 1024:
            return Response({"detail": "Connector file caption exceeds 1024 characters"}, status=400)

        # Connector has a strict initial JPEG/PNG/PDF pilot, consistent with
        # its native inbound contract. Validate before claiming a conversation.
        content = upload.read()
        if is_connector:
            signatures = {
                "image/jpeg": ((".jpg", ".jpeg"), b"\xff\xd8\xff"),
                "image/png": ((".png",), b"\x89PNG\r\n\x1a\n"),
                "application/pdf": ((".pdf",), b"%PDF-"),
            }
            item = signatures.get(content_type)
            if not item or not name.lower().endswith(item[0]) or not content.startswith(item[1]):
                return Response({"detail": t("conversations.files_unavailable_channel")}, status=400)

        claimed = claim_for_reply(self, request, conversation)
        if isinstance(claimed, Response):
            return claimed
        conversation = claimed

        if not is_connector:
            identity = ConnectionIdentity.objects.filter(connection=connection, contact=conversation.contact).first()
            sent = transports.send_file(
                connection,
                chat_id=conversation.external_chat_id,
                user_id=identity.external_user_id if identity else "",
                content=content,
                filename=name,
                content_type=content_type,
                caption=caption,
            )
            if not sent:
                return Response({"detail": t("conversations.file_send_failed")}, status=502)
        message = Message.objects.create(
            conversation=conversation,
            author_type=MessageAuthor.OPERATOR,
            author_user=request.user,
            kind=MessageKind.FILE,
            text=caption,
            attachment_name=name,
            attachment_content_type=content_type,
            attachment_size=len(content),
        )
        message.attachment.save(name, ContentFile(content), save=False)
        message.save(update_fields=["attachment"])
        if is_connector:
            # Same native attachment, existing Outbox, stable command ID.
            # Provider upload runs later in the independent adapter.
            queue_operator_file(
                context=request.tenant_context,
                conversation=conversation,
                message=message,
                content=content,
            )
        conversation.last_activity_at = timezone.now()
        conversation.expected_responder = ExpectedResponder.CUSTOMER
        conversation.save(update_fields=["last_activity_at", "expected_responder"])
        self._audit(request, "file_queued" if is_connector else "file_sent", conversation)
        return Response({"message": message_payload(message)}, status=201)
