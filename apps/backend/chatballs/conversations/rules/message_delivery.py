"""Отправка клиенту сообщения, записанного действием правила.

Сообщение уходит через подключение, в котором идёт обращение, — туда же, куда
отвечает сотрудник. Отправка стоит вне транзакции: мессенджер может отвечать
секунды. Сбой транспорта возвращает событие в outbox на повтор; гарантии
«ровно один раз» у внешней доставки нет и здесь.
"""

from __future__ import annotations

from chatballs.conversations import transports
from chatballs.conversations.models import ConnectionIdentity, LifecycleState, Message
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


class DeliveryFailed(Exception):
    """Транспорт не принял сообщение. Текст сообщения в ошибку не попадает."""


def _target(payload: dict, context: TenantContext):
    """Куда и что отправлять — или None, если отправлять уже некуда."""
    message = (
        Message.objects.select_related("conversation__connection")
        .filter(pk=payload.get("messageId"), organization_id=context.organization_id)
        .first()
    )
    if message is None:
        return None
    conversation = message.conversation
    if conversation.connection is None or conversation.lifecycle != LifecycleState.OPEN:
        return None
    identity = ConnectionIdentity.objects.filter(
        connection=conversation.connection, contact_id=conversation.contact_id
    ).first()
    return (
        conversation.connection,
        conversation.external_chat_id,
        identity.external_user_id if identity else "",
        message.text,
    )


def deliver_rule_message(payload: dict, context: TenantContext) -> None:
    with tenant_atomic(context):
        target = _target(payload, context)
    if target is None:
        return
    connection, chat_id, user_id, text = target
    if not transports.send_reply(connection, chat_id=chat_id, user_id=user_id, text=text):
        raise DeliveryFailed(f"connection {connection.pk} rejected rule message")
