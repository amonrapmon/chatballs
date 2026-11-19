"""Что делать с результатом хода AI: ответ клиенту либо передача оператору.

Отделено от оркестрации (chatballs.conversations.ai_turn) намеренно: там —
порядок шагов и границы транзакций, здесь — правила диалога. Обе функции
вызывают внутри транзакции и обе возвращают текст, который нужно отправить
клиенту: сама отправка — это сеть, и её место снаружи транзакции.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from chatballs.ai.runtime import HANDOFF_TOKEN
from chatballs.api_connector.outbound import ConnectorAIReplyTooLarge, queue_text_command
from chatballs.conversations.ai_reply_delivery import (
    bind_reply,
    record_reply,
    reply_route,
)
from chatballs.conversations.domain_events import (
    record_queue_entry,
)
from chatballs.conversations.gateway_delivery import enqueue_gateway_delivery
from chatballs.conversations.models import (
    AiTurnState,
    ExpectedResponder,
    Message,
    MessageAuthor,
    SystemEvent,
)
from chatballs.conversations.queue import QUEUE_FIELDS, enter_queue
from chatballs.i18n import customer_language, t
from chatballs.integrations.models import IntegrationProvider
from chatballs.native_mirror.publication import queue_ai_publication
from chatballs.notifications.models import NotificationAudience, NotificationType
from chatballs.notifications.services import notify, notify_management
from chatballs.tenancy.context import TenantContext

if TYPE_CHECKING:  # pragma: no cover - только для подсказок типов
    from chatballs.conversations.ai_turn import Turn

logger = logging.getLogger(__name__)


def _finish(message: Message | None, state: str) -> None:
    if message is None:
        return
    message.ai_turn_state = state
    message.save(update_fields=["ai_turn_state"])


def _contact_name(turn: Turn) -> str:
    return turn.conversation.contact.name or t("conversations.guest")


def _persist_reply(
    *, turn: Turn, context: TenantContext, text: str, fields=None, route=None, paused_by_turn=False,
) -> None:
    route = route or reply_route(turn)
    connection = turn.conversation.connection
    is_connector = connection is not None and connection.provider == IntegrationProvider.API_CONNECTOR
    if is_connector and not text.strip():
        return
    if is_connector and paused_by_turn:
        route["pausedByTurn"] = True
    message = Message.objects.create(
        conversation=turn.conversation,
        author_type=MessageAuthor.AI,
        text=text,
        **(fields or {}),
    )
    bind_reply(turn, message, route)
    if is_connector:
        queue_text_command(context=context, conversation=turn.conversation, message=message)
        queue_ai_publication(context=context, message=message, revision=turn.mirror_revision)
        return  # Record the public reply fact only once the command is claimed.
    if connection is not None and connection.provider == IntegrationProvider.GATEWAY and text.strip():
        enqueue_gateway_delivery(context=context, message=message)
        queue_ai_publication(
            context=context, message=message, revision=turn.mirror_revision,
        )
    record_reply(message)


def store_answer(*, turn: Turn, context: TenantContext, text: str, prepared=None, handoff=False) -> str:
    """Ответ модели: запись в диалог и, если модель попросила, передача оператору.

    Возвращает текст для отправки клиенту.
    """
    conversation = turn.conversation
    reply = text
    handoff = handoff or (prepared is None and HANDOFF_TOKEN in reply)
    if handoff and prepared is None:
        reply = reply.replace(HANDOFF_TOKEN, "").strip()

    route = reply_route(turn)
    fields = prepared.message_fields(representation=route["representation"]) if prepared else {}
    conversation.last_activity_at = timezone.now()
    if handoff:
        entered = enter_queue(conversation)
    else:
        conversation.expected_responder = ExpectedResponder.CUSTOMER
    conversation.save(update_fields=[*QUEUE_FIELDS, "last_activity_at"])
    turn.control_version = conversation.ai_control_version
    if conversation.connection is not None and conversation.connection.provider == IntegrationProvider.API_CONNECTOR:
        try:
            with transaction.atomic():
                _persist_reply(
                    turn=turn, context=context, text=reply, fields=fields, route=route, paused_by_turn=handoff,
                )
        except ConnectorAIReplyTooLarge as error:
            return store_failure(turn=turn, context=context, error=error)
    else:
        _persist_reply(turn=turn, context=context, text=reply, fields=fields, route=route)
    record_queue_entry(conversation, entered=handoff and entered, actor_kind="AI")
    _finish(turn.message, AiTurnState.DONE)

    if handoff:
        Message.objects.create(
            conversation=conversation,
            author_type=MessageAuthor.SYSTEM,
            system_event=SystemEvent.AI_HANDED_OVER,
            text="AI передал диалог оператору",
        )
        notify(
            context=context,
            type=NotificationType.OPERATOR_REQUESTED,
            audience=NotificationAudience.OPERATORS,
            audience_group=conversation.group,
            title=f"AI передал диалог · {_contact_name(turn)}",
            title_key="notifications.ai_handed_over",
            text_params={"contact": _contact_name(turn)},
            body=turn.query[:120],
            target_id=conversation.id,
            source_type="Conversation",
            source_id=conversation.id,
            dedup_key=f"handoff:{conversation.id}",
        )
    return reply


def store_voice_without_transcript(*, turn: Turn, context: TenantContext) -> None:
    """Отвечать не на что: голосовое без стенограммы уходит оператору.

    Это не сбой AI, и клиент не должен видеть извинений за поломку: ему просто
    ответит человек.
    """
    conversation = turn.conversation
    entered = enter_queue(conversation)
    conversation.save(update_fields=QUEUE_FIELDS)
    record_queue_entry(conversation, entered=entered, actor_kind="AI")
    _finish(turn.message, AiTurnState.FAILED)
    if turn.is_new_conversation:
        # Про новый диалог операторов уже позвали при приёме.
        return
    notify(
        context=context,
        type=NotificationType.OPERATOR_REQUESTED,
        audience=NotificationAudience.OPERATORS,
        audience_group=conversation.group,
        title=f"Нужен оператор · {_contact_name(turn)}",
        title_key="notifications.operator_needed",
        text_params={"contact": _contact_name(turn)},
        body="Голосовое без расшифровки",
        body_key="notifications.voice_without_transcript",
        target_id=conversation.id,
        source_type="Conversation",
        source_id=conversation.id,
        dedup_key=f"media:{conversation.id}",
    )


def store_failure(*, turn: Turn, context: TenantContext, error: object) -> str:
    """Ответа не будет: диалог уходит оператору, клиент получает понятный текст.

    Сбой AI не должен «терять» сообщение — ни отказ провайдера, ни ход,
    просроченный в очереди.
    """
    conversation = turn.conversation
    channel = conversation.channel
    logger.warning("AI turn failed for conversation %s: %s", conversation.id, error)

    entered = enter_queue(conversation)
    conversation.last_activity_at = timezone.now()
    conversation.save(update_fields=[*QUEUE_FIELDS, "last_activity_at"])
    record_queue_entry(conversation, entered=entered, actor_kind="AI")
    # This failure intentionally entered the employee queue under the same lock.
    # Bind its own notification to that transition; later takeovers still revoke it.
    turn.control_version = conversation.ai_control_version
    Message.objects.create(
        conversation=conversation,
        author_type=MessageAuthor.SYSTEM,
        system_event=SystemEvent.AI_UNAVAILABLE,
        text="AI недоступен — диалог передан оператору",
    )
    fallback = t(
        "conversations.ai_unavailable_reply",
        language=customer_language(channel.organization),
    )
    _finish(turn.message, AiTurnState.FAILED)
    turn.control_version = conversation.ai_control_version
    _persist_reply(turn=turn, context=context, text=fallback, paused_by_turn=True)

    notify(
        context=context,
        type=NotificationType.OPERATOR_REQUESTED,
        audience=NotificationAudience.OPERATORS,
        audience_group=conversation.group,
        title=f"Нужен оператор · {_contact_name(turn)}",
        title_key="notifications.operator_needed",
        text_params={"contact": _contact_name(turn)},
        body="AI временно недоступен, диалог ждёт ответа",
        body_key="notifications.ai_unavailable_waiting",
        target_id=conversation.id,
        source_type="Conversation",
        source_id=conversation.id,
        dedup_key=f"aifail:{conversation.id}",
    )
    notify_management(
        context=context,
        type=NotificationType.AI_STOPPED,
        title=f"Ошибка AI · {channel.name}",
        body="AI временно недоступен, диалог передан оператору",
        title_key="notifications.ai_error",
        body_key="notifications.ai_unavailable_handed_over",
        text_params={"channel": channel.name},
        target_id=conversation.id,
        source_type="Conversation",
        source_id=conversation.id,
        dedup_key=f"aierror:{conversation.id}",
    )
    return fallback
