import uuid

from chatballs.conversations.ai_turn import conversation_is_thinking
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    LifecycleState,
    Message,
    MessageKind,
)
from chatballs.conversations.transports.base import InboundMessage
from chatballs.webchat.configuration import public_config as public_config
from chatballs.webchat.models import WebSession
from chatballs.webchat.sessions import (
    hash_session_token as hash_session_token,
)
from chatballs.webchat.sessions import (
    issue_session as issue_session,
)
from chatballs.webchat.sessions import (
    origin_allowed as origin_allowed,
)
from chatballs.webchat.sessions import (
    resolve_session as resolve_session,
)
from chatballs.webchat.sessions import (
    web_connection_for_channel as web_connection_for_channel,
)

_STATE = {ControlMode.AI: "ai", ControlMode.HUMAN: "operator", ControlMode.PAUSED: "waiting"}
_ROLE = {"CONTACT": "client", "AI": "ai", "OPERATOR": "operator", "SYSTEM": "system"}


def post_message(session: WebSession, text: str) -> None:
    inbound = InboundMessage(
        external_id=uuid.uuid4().hex,
        user_id=session.identity.external_user_id,
        chat_id="",
        text=text,
        display_name=session.identity.display_name,
    )
    ingest_inbound(session.connection, inbound)
    _remember_widget(session)


def post_voice(session: WebSession, *, content: bytes, content_type: str, duration: int) -> None:
    """Голосовое из виджета: байты приходят телом запроса, скачивать нечего."""
    inbound = InboundMessage(
        external_id=uuid.uuid4().hex,
        user_id=session.identity.external_user_id,
        chat_id="",
        text="",
        display_name=session.identity.display_name,
        voice_content=content,
        voice_mime=content_type,
        voice_duration=duration,
    )
    ingest_inbound(session.connection, inbound)
    _remember_widget(session)


def post_file(session: WebSession, *, content: bytes, filename: str, content_type: str, caption: str = "") -> None:
    """Файл из виджета: байты приходят телом запроса, подпись — текстом."""
    from chatballs.conversations.transports.base import (
        InboundFile,
        guess_content_type,
        safe_filename,
    )

    name = safe_filename(filename)
    mime = content_type or guess_content_type(name)
    inbound = InboundMessage(
        external_id=uuid.uuid4().hex,
        user_id=session.identity.external_user_id,
        chat_id="",
        text=caption,
        display_name=session.identity.display_name,
        files=(InboundFile(name=name, content_type=mime, size=len(content), content=content, is_image=mime.startswith("image/")),),
    )
    ingest_inbound(session.connection, inbound)
    _remember_widget(session)


def _remember_widget(session: WebSession) -> None:
    conversation = (
        Conversation.objects.filter(
            channel=session.connection.channel,
            contact=session.identity.contact,
            lifecycle=LifecycleState.OPEN,
        )
        .order_by("-last_activity_at")
        .first()
    )
    if conversation is not None:
        metadata = conversation.transport_meta or {}
        if "webChatWidgetId" not in metadata:
            conversation.transport_meta = {
                **metadata,
                "webChatWidgetId": session.widget_id,
            }
            conversation.save(update_fields=["transport_meta"])


def normalize_phone(raw: str) -> str:
    """Нормализация телефона из формы виджета: только + и цифры, 10–15 цифр."""
    phone = "".join(ch for ch in raw if ch.isdigit() or ch == "+")
    if phone.count("+") > 1 or (phone and "+" in phone[1:]):
        return ""
    digits = phone.lstrip("+")
    if not (10 <= len(digits) <= 15):
        return ""
    return phone


def post_contact(session: WebSession, phone: str) -> None:
    # Ответ клиента на запрос контакта: сообщение без текста, с телефоном —
    # ingest сохранит его в Contact.phone и подтвердит без AI-хода.
    inbound = InboundMessage(
        external_id=uuid.uuid4().hex,
        user_id=session.identity.external_user_id,
        chat_id="",
        text="",
        display_name=session.identity.display_name,
        phone=phone,
    )
    ingest_inbound(session.connection, inbound)


def _call_payload(session: WebSession) -> dict | None:
    # Приглашение на звонок для активной session (SPEC-CHATBALLS-0013 §7.1):
    # виджет получает его этим же поллингом, без отдельного realtime-канала.
    from chatballs.calls.serializers import public_invite_payload
    from chatballs.calls.services import webchat_active_call

    call = webchat_active_call(session.identity)
    if call is None:
        return None
    return public_invite_payload(call, call.invite.expires_at)


def _thread_is_gone(session: WebSession, since: int) -> bool:
    """Переписка, которую показывает виджет, перестала существовать.

    Диалог могли удалить в рабочем месте — вместе со всеми сообщениями. Тогда
    сообщения, до которого досчитал виджет, больше нет, и показывать клиенту
    переписку, которой не существует, нельзя. Закрытый диалог под это правило
    не подпадает: его сообщения на месте.
    """
    return since > 0 and not Message.objects.filter(
        id=since,
        conversation__contact_id=session.identity.contact_id,
        conversation__channel_id=session.connection.channel_id,
    ).exists()


def messages_payload(session: WebSession, since: int) -> dict:
    conversation = (
        Conversation.objects.filter(
            channel=session.connection.channel, contact=session.identity.contact, lifecycle=LifecycleState.OPEN
        )
        .order_by("-last_activity_at")
        .first()
    )
    reset = _thread_is_gone(session, since)
    if reset:
        # Лента виджета начинается заново: то, что осталось, отдаётся целиком.
        since = 0
    if conversation is None:
        return {
            "state": "ai",
            "lifecycle": LifecycleState.OPEN,
            "messages": [],
            "call": None,
            "reset": reset,
            "thinking": False,
        }
    items = conversation.messages.filter(id__gt=since).order_by("created_at")
    return {
        "reset": reset,
        "state": _STATE.get(conversation.control_mode, "ai"),
        "lifecycle": conversation.lifecycle,
        # Ответ уже считается: виджет показывает клиенту, что агент печатает.
        "thinking": conversation_is_thinking(conversation.id),
        "messages": [
            {
                "id": m.id,
                "author": _ROLE.get(m.author_type, "ai"),
                "kind": m.kind,
                "text": m.text,
                "createdAt": m.created_at.isoformat(),
                "durationSeconds": m.duration_seconds,
                "hasAudio": bool(m.audio),
                **(
                    {
                        "attachment": {
                            "name": m.attachment_name,
                            "contentType": m.attachment_content_type,
                            "size": m.attachment_size,
                            "available": bool(m.attachment),
                        }
                    }
                    if m.kind == MessageKind.FILE
                    else {}
                ),
            }
            for m in items
        ],
        "call": _call_payload(session),
    }
