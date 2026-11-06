"""The existing employee voice-send command and its original checks."""

import hashlib

from django.core.files.base import ContentFile
from django.utils import timezone

from chatballs.api_connector.media_validation import verify_media
from chatballs.api_connector.outbound import outbound_available, queue_operator_voice
from chatballs.conversations import transports
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
from chatballs.conversations.reply_problems import problem
from chatballs.integrations.features import voice_messages_allowed
from chatballs.integrations.models import IntegrationProvider

MAX_VOICE_BYTES = 10 * 1024 * 1024
ALLOWED_AUDIO_TYPES = ("audio/ogg", "audio/webm", "audio/mpeg", "audio/mp4", "audio/wav")


@media_operation(MessageKind.VOICE)
def send_voice_reply(*, context, conversation, upload, duration=0, operation_id=None, request=None):
    if conversation.lifecycle != LifecycleState.OPEN:
        return problem("conversations.closed", 409)
    connection = conversation.connection
    is_connector = connection is not None and connection.provider == IntegrationProvider.API_CONNECTOR
    if is_connector:
        if (connection.config.get("connectorMediaOutboundEnabled") is not True
                or not outbound_available(connection)):
            return problem("conversations.voice_unavailable_channel")
    elif connection is None or not transports.supports_voice_send(connection):
        return problem("conversations.voice_unavailable_channel")
    if not voice_messages_allowed(connection):
        return problem("conversations.voice_off_entry_point")
    if upload is None:
        return problem("conversations.attach_audio")
    if upload.size > MAX_VOICE_BYTES:
        return problem("conversations.audio_too_large")
    content_type = (upload.content_type or "audio/ogg").split(";")[0]
    if content_type not in ALLOWED_AUDIO_TYPES:
        return problem("conversations.audio_format_unsupported")
    try:
        duration = max(0, int(duration))
    except (TypeError, ValueError):
        duration = 0
    content = upload.read()
    if is_connector:
        suffixes = {
            "audio/ogg": ".ogg", "audio/webm": ".webm",
            "audio/mpeg": ".mp3", "audio/mp4": ".m4a", "audio/wav": ".wav",
        }
        try:
            verify_media(
                content=content, filename="voice" + suffixes[content_type],
                content_type=content_type, size=len(content),
                sha256=hashlib.sha256(content).hexdigest(), kind="voice",
            )
        except ValueError:
            return problem("conversations.audio_format_unsupported")
        duration = min(duration, 86400)
    conversation = claim_reply(context=context, conversation_id=conversation.pk,
        operation_id=operation_id, request=request)
    identity = ConnectionIdentity.objects.filter(connection=connection, contact=conversation.contact).first()
    if not is_connector and not transports.send_voice(connection, chat_id=conversation.external_chat_id,
            user_id=identity.external_user_id if identity else "", content=content,
            content_type=content_type, duration=duration):
        return problem("conversations.voice_send_failed", 502)
    message = Message.objects.create(conversation=conversation, author_type=MessageAuthor.OPERATOR,
        author_user=context.actor_user, kind=MessageKind.VOICE, audio_content_type=content_type,
        duration_seconds=duration)
    suffix = "ogg" if "ogg" in content_type else content_type.rsplit("/", 1)[-1]
    message.audio.save(f"voice.{suffix}", ContentFile(content), save=False)
    message.save(update_fields=["audio"])
    if is_connector:
        queue_operator_voice(context=context, conversation=conversation, message=message, content=content)
    conversation.last_activity_at = timezone.now()
    conversation.expected_responder = ExpectedResponder.CUSTOMER
    conversation.save(update_fields=["last_activity_at", "expected_responder"])
    audit_reply(context, "voice_queued" if is_connector else "voice_sent", conversation, request=request)
    return message
