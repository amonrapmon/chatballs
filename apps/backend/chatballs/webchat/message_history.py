"""Публичная история виджета: сообщения, состояние и приглашение на звонок."""

from chatballs.conversations.ai_turn import conversation_is_thinking
from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    LifecycleState,
    Message,
    MessageKind,
    SystemEvent,
)
from chatballs.webchat.models import WebSession

_STATE = {ControlMode.AI: "ai", ControlMode.HUMAN: "operator", ControlMode.PAUSED: "waiting"}
_ROLE = {"CONTACT": "client", "AI": "ai", "OPERATOR": "operator", "SYSTEM": "system"}


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
    # Изменения сайта адресованы оператору: клиенту не нужна пустая системная строка.
    items = conversation.messages.filter(id__gt=since).exclude(
        system_event=SystemEvent.SITE_FIELDS_UPDATED,
    ).order_by("created_at")
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
