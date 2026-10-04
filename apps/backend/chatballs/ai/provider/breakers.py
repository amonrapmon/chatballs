"""Предохранители провайдеров: свой на каждую интеграцию каждой организации."""

from __future__ import annotations

from dataclasses import dataclass

from chatballs.ai.provider import routing
from chatballs.ai.provider.resilience import CircuitBreaker


# Предохранитель считает сбои по ключу «организация + интеграция»: провайдер у
# каждой организации свой, и отозванный ключ одной не имеет отношения к AI
# остальных. Общий на процесс предохранитель гасил AI у всех сразу.
@dataclass(slots=True)
class _BreakerSlot:
    revision: int
    breaker: CircuitBreaker


_breakers: dict[tuple[int, int], _BreakerSlot] = {}


def breaker_for(key: tuple[int, int], revision: int) -> CircuitBreaker:
    slot = _breakers.get(key)
    if slot is None or slot.revision != revision:
        slot = _BreakerSlot(revision=revision, breaker=CircuitBreaker())
        _breakers[key] = slot
    return slot.breaker


def reset_breakers() -> None:
    """Для тестов: забыть накопленные сбои провайдеров."""

    _breakers.clear()


def breaker_identity(channel) -> tuple[tuple[int, int], int]:
    """Ключ предохранителя. Без канала провайдер может быть только тестовым —
    считать сбои там не по чему, и общий ключ (0, 0) никому не мешает."""

    if channel is None:
        return (0, 0), 0
    integration_id, revision = routing.integration_runtime_identity(channel)
    return (channel.organization_id, integration_id), revision
