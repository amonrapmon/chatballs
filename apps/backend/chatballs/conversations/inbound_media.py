import logging

from chatballs.conversations import transports
from chatballs.conversations.models import Message, MessageKind
from chatballs.conversations.transports.base import InboundMessage

logger = logging.getLogger(__name__)


def _store_attachment(integration, inbound_file, message: Message) -> None:
    """Скачивание и сохранение файла/фото. Сбой скачивания не теряет сообщение:
    остаётся текстовая заглушка с именем файла."""
    from django.core.files.base import ContentFile

    try:
        content, content_type = transports.download_file(integration, inbound_file)
    except Exception as error:  # noqa: BLE001 - провайдер/сеть, деградация мягкая
        logger.warning("Attachment download failed for message %s: %s", message.id, error)
        message.kind = MessageKind.TEXT
        message.text = f"Файл «{inbound_file.name or 'без имени'}» (не удалось загрузить)"
        message.save(update_fields=["kind", "text"])
        return
    name = inbound_file.name or ("photo.jpg" if inbound_file.is_image else "file")
    message.attachment_name = name
    message.attachment_content_type = content_type
    message.attachment_size = len(content)
    message.attachment.save(name, ContentFile(content), save=False)
    message.save(update_fields=["attachment", "attachment_name", "attachment_content_type", "attachment_size"])


def _store_voice(integration, inbound: InboundMessage, message: Message) -> None:
    """Скачивание и сохранение голосового. Сбой скачивания не теряет сообщение:
    остаётся текстовая заглушка без аудио."""
    from django.core.files.base import ContentFile

    try:
        content, content_type = transports.download_voice(integration, inbound)
    except Exception as error:  # noqa: BLE001 - провайдер/сеть, деградация мягкая
        logger.warning(
            "Voice download failed for message %s: %s", message.id, error
        )
        message.kind = MessageKind.TEXT
        message.text = "Голосовое сообщение (не удалось загрузить)"
        message.save(update_fields=["kind", "text"])
        return
    suffix = "ogg" if "ogg" in content_type else content_type.rsplit("/", 1)[-1][:8] or "bin"
    message.audio_content_type = content_type
    message.duration_seconds = inbound.voice_duration
    message.audio.save(f"voice.{suffix}", ContentFile(content), save=False)
    message.save(update_fields=["audio", "audio_content_type", "duration_seconds"])
