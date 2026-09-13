"""Оповещения о диалогах: сервер сообщает, что изменилось, а не что показать.

Клиент до сих пор опрашивал сервер: список раз в четыре секунды, карточку и
дельту истории — раз в три. Окна сделали каждый запрос дешёвым, но не
бесплатным: на оператора выходило под сорок запросов в минуту, и новое
сообщение всё равно появлялось с задержкой.

Событие несёт только повод обновиться. Данные клиент забирает обычным REST'ом,
где и живёт проверка видимости: канал не решает, кому что показывать, и потому
не может ошибиться в этом. По той же причине событие инбокса не содержит
идентификаторов — сотрудник видит не все диалоги организации.
"""

from __future__ import annotations

from chatballs.realtime import publish

INBOX_EVENT = "inbox.changed"
CONVERSATION_EVENT = "conversation.changed"


def inbox_group(organization_id: int) -> str:
    return f"inbox.{organization_id}"


def conversation_group(conversation_id: int) -> str:
    return f"conv.{conversation_id}"


def notify_inbox_changed(organization_id: int) -> None:
    publish(inbox_group(organization_id), {"type": INBOX_EVENT})


def notify_conversation_changed(conversation_id: int, *, organization_id: int) -> None:
    publish(
        conversation_group(conversation_id),
        {"type": CONVERSATION_EVENT, "conversationId": conversation_id},
    )
    notify_inbox_changed(organization_id)
