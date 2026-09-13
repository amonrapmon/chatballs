"""Кто из сотрудников сейчас за рабочим местом.

Присутствие берётся из открытого сокета, а не из отдельной подсистемы: сокет и
есть признак того, что приложение открыто. Отдельная «доступность» со статусами,
сменами и графиками — это другая, большая задача, и для того, ради чего
присутствие понадобилось, она не нужна.

Хранится не флаг, а момент последней активности. Флага хватало очереди («есть ли
кому заметить»), но выбору ответственного нужно ещё и «не в приложении · 25
минут»: разница между «вышел налить кофе» и «ушёл вчера» — это разница между
хорошим и плохим назначением. Отметка обновляется на подключении, на heartbeat
раз в минуту и на обрыве, поэтому оборванное соединение само перестаёт быть
присутствием, без уборщика.

Это подсказка, а не право. Ошибиться она может в обе стороны: ноутбук уснул, а
отметка ещё свежая; сеть моргнула, и человек на секунду «исчез». Поэтому ни один
доступ и ни одна доставка на присутствии не стоят — оно только помогает решить,
сколько ещё ждать и кого предложить первым.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from django.core.cache import cache
from django.utils import timezone

# Клиент шлёт heartbeat раз в минуту; запас вдвое с небольшим покрывает
# пропущенный тик и не держит призраков дольше пары минут.
ONLINE_WITHIN_SECONDS = 150
# Сколько помним ушедшего, чтобы сказать, как давно его нет. Дольше суток это
# уже не «недавно вышел», а «здесь не работает», и точность не нужна.
REMEMBER_SECONDS = 24 * 3600


def _key(organization_id: int, user_id: int) -> str:
    return f"presence:{organization_id}:{user_id}"


def touch(organization_id: int, user_id: int) -> None:
    """Отметить, что человек сейчас в приложении."""
    cache.set(_key(organization_id, user_id), timezone.now().timestamp(), REMEMBER_SECONDS)


def last_seen(organization_id: int, user_ids: Iterable[int]) -> dict[int, datetime]:
    """Когда каждого из перечисленных видели в последний раз."""
    wanted = list(user_ids)
    if not wanted:
        return {}
    keys = {_key(organization_id, user_id): user_id for user_id in wanted}
    found = cache.get_many(list(keys))
    return {
        keys[key]: datetime.fromtimestamp(value, tz=timezone.get_current_timezone())
        for key, value in found.items()
        if isinstance(value, (int, float))
    }


def online_user_ids(organization_id: int, user_ids: Iterable[int]) -> set[int]:
    """Кто из перечисленных на месте прямо сейчас."""
    now = timezone.now()
    return {
        user_id
        for user_id, seen in last_seen(organization_id, user_ids).items()
        if (now - seen).total_seconds() <= ONLINE_WITHIN_SECONDS
    }
