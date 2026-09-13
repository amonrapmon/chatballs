"""Оповещение сотрудника о том, что у него появились уведомления.

Событие адресное — в сокет каждого получателя отдельно. Группа организации, на
которой живут события инбокса, здесь не годится: уведомления сотрудник видит не
все, и рассылка на организацию означала бы, что о чужих он как минимум узнаёт.

Как и у диалогов, событие несёт только повод перезапросить: ни текста, ни
идентификаторов. Содержимое клиент забирает обычным запросом, где и живёт
проверка видимости — канал о ней не знает и потому не может в ней ошибиться.
"""

from __future__ import annotations

from collections.abc import Iterable

from chatballs.realtime import publish

NOTIFICATIONS_EVENT = "notifications.changed"


def user_group(user_id: int) -> str:
    return f"user.{user_id}"


def notify_notifications_changed(user_ids: Iterable[int]) -> None:
    for user_id in set(user_ids):
        publish(user_group(user_id), {"type": NOTIFICATIONS_EVENT})
