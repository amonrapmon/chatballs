"""Вложения ВКонтакте: разбор входящих и загрузка исходящих.

Разбор здесь чистый — на вход словарь сообщения, на выход значения для
``InboundMessage``. Загрузка идёт в три шага (получить адрес загрузки, залить
файл, сохранить его у провайдера), поэтому наружу она принимает вызов API и
прокси подключения, а не само подключение: так модуль не зависит от транспорта
и проверяется без базы.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from chatballs.conversations.transports.base import (
    InboundFile,
    first,
    guess_content_type,
    request_json_multipart,
    safe_filename,
)

logger = logging.getLogger(__name__)

# Вложения, которые канал умеет показать оператору. Остальные (видео, товар,
# запись на стене) ВКонтакте отдаёт только по отдельному запросу с правами,
# которых у сообщества нет.
KNOWN_ATTACHMENTS = ("photo", "doc", "audio_message", "sticker", "graffiti")


def photo_url(photo: dict) -> str:
    """Самый крупный размер фотографии.

    Набор размеров зависит от исходника, поэтому выбираем по площади, а не по
    буквенному типу: у маленьких снимков крупных типов просто нет.
    """
    sizes = [size for size in (photo.get("sizes") or []) if size.get("url")]
    if not sizes:
        return ""
    largest = max(sizes, key=lambda size: int(size.get("width") or 0) * int(size.get("height") or 0))
    return str(largest.get("url") or "")


def voice_attachment(message: dict) -> tuple[str, int, str, bool]:
    """Голосовое сообщение: адрес, длительность, mime и признак «нечего скачать».

    Последнее значение означает, что голосовое в сообщении было, а адреса в нём
    нет. Такая реплика всё равно доезжает до оператора заглушкой: молча терять
    сказанное клиентом нельзя.
    """
    for attachment in message.get("attachments") or []:
        if attachment.get("type") != "audio_message":
            continue
        payload = attachment.get("audio_message") or {}
        ogg = str(payload.get("link_ogg") or "")
        url = ogg or str(payload.get("link_mp3") or "")
        duration = int(payload.get("duration") or 0)
        return url, duration, ("audio/ogg" if ogg else "audio/mpeg") if url else "", not url
    return "", 0, "", False


def file_attachments(message: dict) -> tuple[InboundFile, ...]:
    """Фото, документы, стикеры и граффити — каждый становится своей репликой."""
    files: list[InboundFile] = []
    for attachment in message.get("attachments") or []:
        kind = attachment.get("type")
        if kind == "photo":
            url = photo_url(attachment.get("photo") or {})
            if url:
                files.append(InboundFile(name="photo.jpg", content_type="image/jpeg", url=url, is_image=True))
        elif kind in ("sticker", "graffiti"):
            url = _image_from_list(attachment.get(kind) or {})
            if url:
                files.append(InboundFile(name=f"{kind}.png", content_type="image/png", url=url, is_image=True))
        elif kind == "doc":
            document = attachment.get("doc") or {}
            url = str(document.get("url") or "")
            if not url:
                continue
            name = safe_filename(document.get("title") or "", "document")
            mime = guess_content_type(name)
            files.append(
                InboundFile(
                    name=name,
                    content_type=mime,
                    size=int(document.get("size") or 0),
                    url=url,
                    is_image=mime.startswith("image/"),
                )
            )
    return tuple(files)


def unsupported_attachments(message: dict) -> tuple[str, ...]:
    """Типы вложений, которые разобрать не удалось, — для журнала."""
    return tuple(
        str(attachment.get("type") or "")
        for attachment in message.get("attachments") or []
        if attachment.get("type") not in KNOWN_ATTACHMENTS
    )


def _image_from_list(payload: dict) -> str:
    """Самая крупная картинка стикера или граффити."""
    images = [image for image in (payload.get("images") or []) if image.get("url")]
    if not images:
        return str(payload.get("url") or "")
    largest = max(images, key=lambda image: int(image.get("width") or 0) * int(image.get("height") or 0))
    return str(largest.get("url") or "")


def upload_attachment(
    *,
    api: Callable[..., object],
    proxy_url: str,
    peer_id: str,
    content: bytes,
    filename: str,
    content_type: str,
) -> str:
    """Загрузить файл и вернуть строку attachment для messages.send.

    Фото и документы у ВКонтакте загружаются разными парами методов, но шаги
    одинаковы: получить адрес загрузки, отправить файл на него, сохранить
    результат. Пустая строка — загрузка не удалась, отправку продолжать нечем.
    """
    as_photo = content_type in ("image/jpeg", "image/png", "image/gif", "image/webp")
    if as_photo:
        server = api("photos.getMessagesUploadServer", {"peer_id": peer_id})
        uploaded = _upload(server, proxy_url=proxy_url, field="photo", filename=filename, content=content, content_type=content_type)
        if not uploaded.get("photo"):
            return ""
        saved = api(
            "photos.saveMessagesPhoto",
            {"server": uploaded.get("server", ""), "photo": uploaded.get("photo", ""), "hash": uploaded.get("hash", "")},
            post=True,
        )
        item = (saved or [{}])[0] if isinstance(saved, list) else {}
        return _attachment_id("photo", item)
    server = api("docs.getMessagesUploadServer", {"type": "doc", "peer_id": peer_id})
    uploaded = _upload(server, proxy_url=proxy_url, field="file", filename=filename, content=content, content_type=content_type)
    if not uploaded.get("file"):
        return ""
    saved = api("docs.save", {"file": uploaded.get("file", "")}, post=True)
    item = (saved or {}).get("doc") or {} if isinstance(saved, dict) else {}
    return _attachment_id("doc", item)


def _upload(server: object, *, proxy_url: str, field: str, filename: str, content: bytes, content_type: str) -> dict:
    upload_url = str((server or {}).get("upload_url") or "") if isinstance(server, dict) else ""
    if not upload_url:
        return {}
    return request_json_multipart(
        upload_url,
        fields={},
        file_field=field,
        filename=filename,
        content=content,
        content_type=content_type,
        proxy_url=proxy_url,
    )


def _attachment_id(kind: str, item: dict) -> str:
    owner_id = first(item, "owner_id", default="")
    item_id = first(item, "id", default="")
    return f"{kind}{owner_id}_{item_id}" if owner_id != "" and item_id != "" else ""
