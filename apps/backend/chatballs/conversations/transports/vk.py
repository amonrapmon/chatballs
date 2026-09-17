"""VK community transport: приём сообщений (Bots Long Poll API).

``groups.getLongPollServer`` отдаёт адрес сервера, ключ и позицию в потоке
событий, дальше сервер опрашивается ``act=a_check``. Отправка живёт в
``vk_send``, разбор вложений — в ``vk_media``, доступ к API — в ``vk_api``.

Позиция потока хранится в ``poll_marker``, а адрес сервера и ключ — в памяти
процесса: их выдают на несколько часов, и колонка под них означала бы запись в
базу на каждом цикле опроса (``transports.backoff`` устроен так же).
"""

from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass, replace

from django.conf import settings

from chatballs.conversations.transports import vk_api, vk_media
from chatballs.conversations.transports.base import InboundMessage, first, request_json
from chatballs.conversations.transports.errors import PollFailed
from chatballs.i18n import customer_language, t
from chatballs.integrations.checks import vk_group
from chatballs.integrations.outbound import mask_url_secrets

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Session:
    server: str
    key: str
    group_id: str


_sessions: dict[int, _Session] = {}


def reset() -> None:
    """Забыть выданные адреса Long Poll (тесты, смена токена подключения)."""
    _sessions.clear()


def _ts(value: object, fallback: str = "") -> str:
    """Позиция потока строкой.

    Ноль — это тоже позиция: у сообщества, которому ещё не писали, ВКонтакте
    отдаёт ``ts: 0``. Обычное ``or`` приняло бы её за отсутствие значения, а
    опрос с пустой позицией возвращает ``ts: -1`` — курсор, с которого поток
    уже не читается.
    """
    return fallback if value is None or value == "" else str(value)


def _group_id(integration) -> str:
    """Идентификатор сообщества: из настроек подключения или у самого ВКонтакте.

    Проверка подключения кладёт его в конфигурацию, но опрос обязан работать и
    до первой проверки: иначе подключение, созданное в обход кнопки
    «Проверить», молча не принимало бы сообщения.
    """
    configured = str(integration.config.get("bot_id") or "")
    if configured:
        return configured
    group_id = str(vk_group(vk_api.call(integration, "groups.getById")).get("id") or "")
    if not group_id:
        raise PollFailed(t("conversations.vk_no_group"))
    return group_id


def _open_session(integration, group_id: str = "") -> tuple[_Session, str]:
    """Новый адрес Long Poll; вторым значением — позиция потока от ВКонтакте."""
    group = group_id or _group_id(integration)
    response = vk_api.call(integration, "groups.getLongPollServer", {"group_id": group}) or {}
    session = _Session(
        server=str(response.get("server") or ""),
        key=str(response.get("key") or ""),
        group_id=group,
    )
    if not session.server or not session.key:
        raise PollFailed(t("conversations.vk_longpoll_unavailable"))
    _sessions[integration.id] = session
    return session, _ts(response.get("ts"))


def _check(integration, session: _Session, ts: str) -> dict:
    query = urllib.parse.urlencode(
        {
            "act": "a_check",
            "key": session.key,
            "ts": ts,
            "wait": settings.CHATBALLS_MESSENGER_POLL_TIMEOUT_SECONDS,
        }
    )
    return request_json(f"{session.server}?{query}", proxy_url=vk_api.proxy(integration))


def _recover(integration, session: _Session, ts: str, data: dict) -> tuple[dict, str]:
    """Ответ ``failed``: позиция устарела (1) либо ключ и история потеряны (2, 3).

    Восстанавливаемся тут же, а не на следующем цикле: иначе подключение висело
    бы с протухшим ключом, а поллер всё это время считал бы, что сообщений
    просто нет.
    """
    failed = int(data.get("failed") or 0)
    if failed == 1:
        ts = _ts(data.get("ts"), ts)
    else:
        session, fresh_ts = _open_session(integration, session.group_id)
        # Потеря истории (3) обесценивает и позицию: со старой сервер не отдаст
        # ничего. Протухший ключ (2) позицию не трогает.
        ts = ts if failed == 2 else fresh_ts
    retried = _check(integration, session, ts)
    if retried.get("failed"):
        raise PollFailed(t("conversations.vk_longpoll_failed", code=retried.get("failed")))
    return retried, ts


def poll_updates(integration) -> tuple[list[InboundMessage], str]:
    if not integration.secret:
        return [], integration.poll_marker
    try:
        session = _sessions.get(integration.id)
        ts = integration.poll_marker
        if session is None or not ts:
            session, fresh_ts = _open_session(integration, session.group_id if session else "")
            ts = ts or fresh_ts
        data = _check(integration, session, ts)
        if data.get("failed"):
            data, ts = _recover(integration, session, ts, data)
        messages = _messages(integration, data.get("updates") or [])
    except vk_api.CALL_ERRORS as error:
        # Сессия могла протухнуть вместе со связью — следующая попытка начнёт с
        # нового адреса, а не с сохранённого мёртвого.
        _sessions.pop(integration.id, None)
        raise PollFailed(mask_url_secrets(error)) from error
    return messages, _ts(data.get("ts"), ts)


def _messages(integration, updates: list) -> list[InboundMessage]:
    inbound = [message for message in (_normalize(integration, u) for u in updates) if message is not None]
    return _with_profiles(integration, inbound)


def _normalize(integration, update: dict) -> InboundMessage | None:
    if update.get("type") != "message_new":
        return None
    payload = update.get("object") or {}
    # С версии 5.103 сообщение лежит в object.message, до неё — прямо в object.
    message = payload.get("message") or payload
    from_id = message.get("from_id")
    peer_id = message.get("peer_id")
    external_id = first(message, "id", "conversation_message_id")
    if from_id is None or peer_id is None or external_id is None:
        return None
    if int(from_id) < 0:
        # Сообщение самого сообщества (ответ из диалогов ВКонтакте) — не входящее.
        return None
    voice_url, voice_duration, voice_mime, voice_unavailable = vk_media.voice_attachment(message)
    files = vk_media.file_attachments(message)
    text = _text(integration, message, has_content=bool(files or voice_url or voice_unavailable))
    if not text and not files and not voice_url and not voice_unavailable:
        return None
    return InboundMessage(
        external_id=str(external_id),
        user_id=str(from_id),
        chat_id=str(peer_id),
        text=text,
        display_name="",
        voice_url=voice_url,
        voice_duration=voice_duration,
        voice_mime=voice_mime,
        voice_unavailable=voice_unavailable,
        files=files,
    )


def _text(integration, message: dict, *, has_content: bool) -> str:
    """Текст реплики; для непоказуемого вложения — след вместо пустоты."""
    text = str(message.get("text") or "")
    unsupported = vk_media.unsupported_attachments(message)
    if unsupported:
        logger.info("VK attachment types not shown to the operator: %s", ", ".join(unsupported))
    if text or has_content or not unsupported:
        return text
    # Вложение, которое канал показать не может: пустой текст обернулся бы
    # потерей реплики, поэтому оператор видит хотя бы её след.
    return t("conversations.attachment_unsupported", language=customer_language(integration.organization))


def _with_profiles(integration, messages: list[InboundMessage]) -> list[InboundMessage]:
    """Имя, логин и фото отправителей — одним запросом на пачку.

    В апдейте ВКонтакте профиля нет, его отдаёт ``users.get``. Спрашивать его на
    каждое сообщение значило бы упереться в частоту обращений на оживлённом
    сообществе, поэтому запрос один на цикл опроса.
    """
    user_ids = sorted({message.user_id for message in messages if message.user_id.isdigit()})
    if not user_ids:
        return messages
    try:
        response = vk_api.call(
            integration,
            "users.get",
            {"user_ids": ",".join(user_ids), "fields": "photo_100,screen_name"},
        )
    except vk_api.CALL_ERRORS as error:
        # Без профиля сообщение всё равно доезжает: имя контакта уточнится на
        # следующем сообщении, а терять реплику из-за справки нельзя.
        logger.warning("VK users.get failed for integration %s: %s", integration.id, mask_url_secrets(error))
        return messages
    profiles = {str(user.get("id")): user for user in (response or []) if isinstance(user, dict)}
    return [_with_profile(message, profiles.get(message.user_id)) for message in messages]


def _with_profile(message: InboundMessage, profile: dict | None) -> InboundMessage:
    if not profile:
        return message
    name = " ".join(part for part in (profile.get("first_name"), profile.get("last_name")) if part)
    screen_name = str(profile.get("screen_name") or "")
    return replace(
        message,
        display_name=str(name or screen_name),
        username=screen_name,
        avatar_url=str(profile.get("photo_100") or ""),
    )


def download_file(integration, url: str, content_type: str) -> tuple[bytes, str]:
    """Скачивание вложения по прямому адресу из апдейта."""
    return vk_api.download(integration, url), content_type or "application/octet-stream"


def download_voice(integration, url: str, content_type: str = "") -> tuple[bytes, str]:
    return vk_api.download(integration, url), content_type or "audio/ogg"
