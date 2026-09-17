"""VK community transport: отправка сообщений (messages.send).

Текст, приглашение на звонок кнопкой-ссылкой и файл оператора. Голосовых здесь
нет намеренно: ВКонтакте принимает голосовое только в ogg/opus, а композер
записывает webm/opus, поэтому VK не зарегистрирован в ``_VOICE_SEND`` и
интерфейс не предлагает записать голосовое в этом канале.
"""

from __future__ import annotations

import functools
import json
import logging
import random

from chatballs.conversations.transports import vk_api, vk_media
from chatballs.i18n import customer_language, t
from chatballs.integrations.outbound import mask_url_secrets

logger = logging.getLogger(__name__)


def _send(integration, *, chat_id: str, user_id: str, params: dict) -> bool:
    target = chat_id or user_id
    if not integration.secret or not target:
        return False
    body = {
        "peer_id": target,
        # random_id обязателен: по нему ВКонтакте отбрасывает повторы. Отправку
        # мы не повторяем, поэтому значение своё на каждый вызов.
        "random_id": random.getrandbits(31),
        **params,
    }
    try:
        # POST: ответ агента длиннее, чем разумно укладывать в адрес запроса.
        vk_api.call(integration, "messages.send", body, post=True)
        return True
    except vk_api.CALL_ERRORS as error:
        logger.warning("VK send failed for integration %s: %s", integration.id, mask_url_secrets(error))
        return False


def send_text(integration, *, chat_id: str, user_id: str, text: str) -> bool:
    return _send(integration, chat_id=chat_id, user_id=user_id, params={"message": text})


def _caption(integration, key: str) -> str:
    """Подпись кнопки читает клиент — язык организации, а не язык запроса."""
    return t(key, language=customer_language(integration.organization))


def send_call_invite(integration, *, chat_id: str, user_id: str, text: str, url: str) -> bool:
    # Приглашение на онлайн-звонок: кнопка-ссылка под сообщением.
    button = {"action": {"type": "open_link", "link": url, "label": _caption(integration, "conversations.button_join_call")}}
    keyboard = {"inline": True, "buttons": [[button]]}
    return _send(
        integration,
        chat_id=chat_id,
        user_id=user_id,
        params={"message": text, "keyboard": json.dumps(keyboard, ensure_ascii=False)},
    )


def send_file(integration, *, chat_id: str, user_id: str, content: bytes, filename: str, content_type: str, caption: str = "") -> bool:
    """Файл оператора: загрузка у провайдера, затем сообщение со ссылкой на неё."""
    target = chat_id or user_id
    if not integration.secret or not target:
        return False
    try:
        attachment = vk_media.upload_attachment(
            api=functools.partial(vk_api.call, integration),
            proxy_url=vk_api.proxy(integration),
            peer_id=target,
            content=content,
            filename=filename,
            content_type=content_type,
        )
    except vk_api.CALL_ERRORS as error:
        logger.warning("VK upload failed for integration %s: %s", integration.id, mask_url_secrets(error))
        return False
    if not attachment:
        return False
    params = {"attachment": attachment, **({"message": caption[:4000]} if caption else {})}
    return _send(integration, chat_id=chat_id, user_id=user_id, params=params)
