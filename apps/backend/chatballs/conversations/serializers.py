from django.db.models import Count, Max, Q

from chatballs.conversations.contact_avatars import contact_avatar_url_in
from chatballs.conversations.models import (
    Conversation,
    Message,
    MessageAuthor,
    MessageKind,
    SystemEvent,
)
from chatballs.conversations.serializer_context import (
    _connection_identity,
    _contact_email,
    _contact_is_guest,
    _conversation_history,
    _history_item,
    _last_message,
)
from chatballs.conversations.site_fields import field_display, site_fields_payload
from chatballs.conversations.tool_call_events import tool_call_payload, tool_call_text
from chatballs.i18n import t
from chatballs.identity.avatars import user_avatar_url_in
from chatballs.integrations.features import features_payload


def _system_text(message: Message) -> str:
    params = message.system_params or {}
    if message.system_event == SystemEvent.TOOL_CALLED:
        return tool_call_text(params)
    # Вид звонка приходит кодом (AUDIO/VIDEO): слово для него — тоже в каталоге.
    if params.get("kind"):
        params = {**params, "kind": t(f"calls.kind_{str(params['kind']).lower()}")}
    if message.system_event == SystemEvent.SITE_FIELDS_UPDATED:
        definition = {"type": params["fieldType"]}
        params = {**params, **{key: field_display(definition, params.get(key)) for key in ("old", "new")}}
    rendered = t(f"conversations.system.{message.system_event}", **params)
    # Ключа нет в каталоге — t вернул сам ключ; тогда честнее показать то, что
    # записано, чем служебный код.
    return message.text if rendered.startswith("conversations.system.") else rendered


def message_payload(message: Message) -> dict[str, object]:
    payload = {
        "id": message.id,
        "author": message.author_type,
        "authorUserId": message.author_user_id,
        # Подпись исходящего сообщения сотрудника (дизайн-базлайн v2, 4a).
        "authorName": (message.author_user.full_name or message.author_user.email) if message.author_user_id and message.author_user else "",
        "authorAvatarUrl": user_avatar_url_in(message.author_user, message.organization_id) if message.author_user_id and message.author_user else None,
        "kind": message.kind,
        "deliveryStatus": message.delivery_status or None,
        "deliveryStatusAt": (
            message.delivery_status_at.isoformat() if message.delivery_status_at else None
        ),
        "deliveryFailureKind": message.delivery_failure_kind or None,
        # Системное событие собирается по коду на языке запроса: историю
        # диалога читают оба — и русскоязычный оператор, и англоязычный, — а
        # записана она один раз. Код без перевода и записи, сделанные до его
        # появления, приходят сохранённым текстом.
        "text": _system_text(message) if message.system_event else message.text,
        # Код нужен интерфейсу ещё и для тона строки: передача — предупреждение,
        # взятие — акцент. Раньше тон угадывался регуляркой по русским словам.
        "systemEvent": message.system_event,
        "contentHtml": message.content_html,
        "createdAt": message.created_at.isoformat(),
    }
    if message.kind == "voice":
        payload["audioUrl"] = (
            f"/api/v1/conversations/messages/{message.id}/audio/" if message.audio else None
        )
        payload["durationSeconds"] = message.duration_seconds
        payload["transcript"] = message.transcript
        payload["transcriptStatus"] = message.transcript_status
    if message.kind == "file":
        payload["attachmentUrl"] = (
            f"/api/v1/conversations/messages/{message.id}/attachment/" if message.attachment else None
        )
        payload["attachmentName"] = message.attachment_name
        payload["attachmentContentType"] = message.attachment_content_type
        payload["attachmentSize"] = message.attachment_size
    if message.system_event == SystemEvent.TOOL_CALLED:
        payload["toolCall"] = tool_call_payload(message.system_params or {})
    return payload


def last_messages_for(conversation_ids: list[int]) -> dict[int, Message]:
    """Последняя реплика каждого диалога страницы — одним запросом.

    Превью строки списка раньше спрашивалось на каждый диалог: тридцать строк
    инбокса стоили тридцати запросов, и обновление списка раз в четыре секунды
    множило их на число операторов.
    """
    if not conversation_ids:
        return {}
    rows = (
        Message.objects.filter(conversation_id__in=conversation_ids)
        .exclude(author_type=MessageAuthor.SYSTEM)
        .select_related("author_user")
        .order_by("conversation_id", "-created_at", "-id")
        .distinct("conversation_id")
    )
    return {message.conversation_id: message for message in rows}


def pending_counts_for(conversation_ids: list[int], read_map: dict[int, int]) -> dict[int, int]:
    """Бейджи непрочитанных для страницы — двумя запросами вместо строки-на-строку.

    Считается хвост клиентских сообщений: те, что пришли после последнего
    ответа AI или оператора и которых просматривающий ещё не открывал.
    """
    if not conversation_ids:
        return {}
    answered = dict(
        Message.objects.filter(conversation_id__in=conversation_ids)
        .exclude(author_type=MessageAuthor.CONTACT)
        .exclude(system_event=SystemEvent.SITE_FIELDS_UPDATED)
        .values("conversation_id")
        .annotate(last_id=Max("id"))
        .values_list("conversation_id", "last_id")
    )
    tail = Q()
    for conversation_id in conversation_ids:
        threshold = max(read_map.get(conversation_id, 0), answered.get(conversation_id, 0))
        tail |= Q(conversation_id=conversation_id, id__gt=threshold)
    counts = (
        Message.objects.filter(author_type=MessageAuthor.CONTACT)
        .filter(tail)
        .values("conversation_id")
        .annotate(total=Count("id"))
        .values_list("conversation_id", "total")
    )
    return dict(counts)


def _pending_count(conversation: Conversation, last_read_id: int = 0) -> int:
    # Бейдж непрочитанных: хвост клиентских сообщений (после последнего ответа
    # AI/оператора), которые просматривающий ещё не открывал (id > отметки
    # прочтения). Открытие диалога двигает отметку — бейдж гаснет.
    count = 0
    for message in conversation.messages.exclude(system_event=SystemEvent.SITE_FIELDS_UPDATED).order_by("-created_at")[:50]:
        if message.author_type != MessageAuthor.CONTACT:
            break
        if message.id > last_read_id:
            count += 1
    return count


def conversation_payload(
    conversation: Conversation,
    *,
    detailed: bool = False,
    last_read_id: int = 0,
    viewer_id: int | None = None,
    last_message: Message | None = None,
    pending_count: int | None = None,
) -> dict[str, object]:
    """Карточка диалога.

    Сообщения в неё не входят ни в одном режиме: история — отдельная лента с
    собственным окном (`/messages/`), иначе открытие диалога с тысячей реплик
    тянуло бы их все, да ещё и на каждом обновлении карточки.
    """
    # Списку превью и бейдж считает страница целиком (last_messages_for,
    # pending_counts_for); поштучный расчёт остаётся для одиночных ответов.
    last = None if detailed else (last_message or _last_message(conversation))
    channel = conversation.channel
    identity = _connection_identity(conversation) if detailed and conversation.contact_id else None
    payload = {
        "id": conversation.id,
        "channel": {
            "id": channel.id,
            "code": channel.code,
            "name": channel.name,
        },
        "connection": (
            {
                "id": conversation.connection_id,
                "provider": conversation.connection.provider,
                "name": conversation.connection.name,
                # Что разрешено в этой точке входа («Настройки → Голосовые и звонки»).
                **features_payload(conversation.connection),
            }
            if conversation.connection_id
            else None
        ),
        "contact": (
            {
                "id": conversation.contact_id,
                "name": conversation.contact.name,
                "phone": conversation.contact.phone,
                "avatarUrl": contact_avatar_url_in(
                    conversation.contact, conversation.organization_id
                ),
                "description": conversation.contact.description,
                "company": conversation.contact.company,
                "city": conversation.contact.city,
                "email": _contact_email(conversation),
                "username": identity.username if identity else "",
                # Для переменной {{client_name}} шаблонов ответов.
                **({"isGuest": _contact_is_guest(conversation.contact, identity)} if detailed else {}),
            }
            if conversation.contact_id
            else None
        ),
        "lifecycle": conversation.lifecycle,
        "controlMode": conversation.control_mode,
        "expectedResponder": conversation.expected_responder,
        "assignedOperatorId": conversation.assigned_operator_id,
        "assignedOperator": (
            {
                "id": conversation.assigned_operator_id,
                "name": (
                    conversation.assigned_operator.full_name
                    or conversation.assigned_operator.email
                ),
                "avatarUrl": user_avatar_url_in(conversation.assigned_operator, conversation.organization_id),
            }
            if conversation.assigned_operator_id
            else None
        ),
        "isAssignedToViewer": bool(
            viewer_id and conversation.assigned_operator_id == viewer_id
        ),
        # Ожидание (макет «Очередь и уведомления», кадры Q3 и Q4): с какого
        # момента диалог ждёт человека и с какого — конкретного человека.
        # Считать «сколько осталось» клиент должен сам: минута на сервере и
        # минута на экране расходятся, и показывать замерший счётчик хуже, чем
        # не показывать никакого.
        "waitingSince": (
            conversation.waiting_since.isoformat() if conversation.waiting_since else None
        ),
        "assignedAt": (
            conversation.assigned_at.isoformat() if conversation.assigned_at else None
        ),
        "group": (
            {"id": conversation.group_id, "name": conversation.group.name, "color": conversation.group.color}
            if conversation.group_id
            else None
        ),
        # Дизайн-базлайн v2: приоритет, метки, заметка, архив.
        "priority": conversation.priority,
        "labels": [
            {"id": label.id, "name": label.name, "color": label.color}
            for label in conversation.labels.all()
        ],
        "note": conversation.note,
        "archivedAt": (
            conversation.archived_at.isoformat() if conversation.archived_at else None
        ),
        "lastActivityAt": conversation.last_activity_at.isoformat(),
        "createdAt": conversation.created_at.isoformat(),
    }
    if detailed:
        payload["siteFields"] = site_fields_payload(conversation.contact, integration_id=conversation.connection_id) if conversation.contact_id else []
        history = _conversation_history(conversation)
        payload["history"] = [_history_item(c) for c in history]
        # Запрос контакта мог уйти когда угодно — в загруженном окне истории его
        # может не быть, поэтому факт запроса считает сервер, а не лента.
        payload["contactRequested"] = conversation.messages.filter(
            kind=MessageKind.CONTACT_REQUEST
        ).exists()
    else:
        payload["lastMessage"] = message_payload(last) if last else None
        payload["pendingCount"] = (
            pending_count if pending_count is not None else _pending_count(conversation, last_read_id)
        )
    return payload
