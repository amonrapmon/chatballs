"""Фото контакта: скачиваем у провайдера и отдаём со своего адреса.

Рабочее место живёт под `Content-Security-Policy: img-src 'self'`, поэтому
ссылка на CDN мессенджера до экрана не доезжает — оператор видит инициалы
вместо лица. Значит, фото должно лежать у нас и отдаваться тенантным
эндпоинтом, как фото сотрудника (`identity.avatars`).

Источник фото запоминается в `Contact.avatar_source`: у MAX это адрес из
профиля отправителя, у Telegram — идентификатор файла фотографии. Пока
источник тот же, повторно ничего не качается. Строка `tg:none` означает «у
человека в Telegram фото нет»: без неё каждое его сообщение стоило бы лишнего
запроса к API.
"""

from __future__ import annotations

import hashlib
import logging

from django.core.files.base import ContentFile

from chatballs.conversations.models import Contact
from chatballs.identity.avatars import image_type, organization_public_id

logger = logging.getLogger(__name__)

MAX_AVATAR_BYTES = 2 * 1024 * 1024
# Проверено и фото нет: помним, чтобы не спрашивать провайдера снова.
NO_AVATAR = "none"


def contact_avatar_url_in(contact: Contact | None, organization_id: int) -> str | None:
    """Ссылка на фото контакта для рабочего места; None — фото нет."""
    if contact is None:
        return None
    if contact.avatar:
        version = hashlib.sha1(contact.avatar.name.encode("utf-8")).hexdigest()[:8]
        public_id = organization_public_id(organization_id)
        return f"/api/v1/organizations/{public_id}/conversations/clients/{contact.id}/avatar/?v={version}"
    # Демо-набор и старые записи держат ссылку на наш же адрес — она рабочая.
    return contact.avatar_url or None


def store_contact_avatar(contact: Contact, *, content: bytes, source: str) -> bool:
    """Сохранить скачанное фото. False — это не картинка или она слишком велика."""
    if not content or len(content) > MAX_AVATAR_BYTES:
        return False
    detected = image_type(content)
    if detected is None:
        return False
    content_type, suffix = detected
    if contact.avatar:
        contact.avatar.delete(save=False)
    contact.avatar.save(f"avatar{suffix}", ContentFile(content), save=False)
    contact.avatar_content_type = content_type
    contact.avatar_source = source[:512]
    contact.save(update_fields=["avatar", "avatar_content_type", "avatar_source"])
    return True


def _checked_marker(source: str) -> str:
    """«Фото по этому источнику спрашивали, его нет» — чтобы не спрашивать снова."""
    return f"{NO_AVATAR}:{source}"[:512]


def refresh_contact_avatar(integration, inbound, contact: Contact) -> None:
    """Подтянуть фото отправителя, если провайдер его отдаёт и оно новое.

    Сбой скачивания не мешает сообщению: фото — украшение карточки, а не её
    содержание.
    """
    from chatballs.conversations import transports

    try:
        source = transports.avatar_source(integration, inbound)
        if not source or contact.avatar_source in (source, _checked_marker(source)):
            return
        fetched = transports.download_avatar(integration, inbound)
        if fetched is None:
            contact.avatar_source = _checked_marker(source)
            contact.save(update_fields=["avatar_source"])
            return
        content, source_key = fetched
        if not store_contact_avatar(contact, content=content, source=source_key):
            logger.info("Contact %s avatar from %s is not an image", contact.id, source_key)
    except Exception as error:  # noqa: BLE001 - провайдер/сеть, деградация мягкая
        logger.info("Contact %s avatar download failed: %s", contact.id, error)
