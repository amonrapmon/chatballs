"""Публикация оповещений в канальный слой.

Транспорт и только транспорт. Какие бывают группы и какие события в них летят,
знают доменные модули (conversations.realtime, notifications.realtime); здесь
единственное в проекте знание про channels — и единственное место, где сбой
канала гасится, чтобы не уронить уже сделанную запись.
"""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def publish(group: str, payload: dict[str, object]) -> None:
    """Оповещение — вспомогательный путь: его сбой не должен ронять запись.

    Данные к моменту отправки уже сохранены; если канал недоступен, клиент
    узнает об изменении следующим опросом — он остаётся как запасной путь.
    """
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(group, {"type": "fanout", "payload": payload})
    except Exception:  # noqa: BLE001 — канал не должен ломать сохранение
        logger.warning("realtime fanout failed for %s", group, exc_info=True)
