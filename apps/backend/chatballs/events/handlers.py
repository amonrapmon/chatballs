import logging
from collections.abc import Callable

from chatballs.events.models import OutboxEvent
from chatballs.events.services import tenant_context_for_event
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict, TenantContext | None], None]
_REGISTRY: dict[str, EventHandler] = {}
# Обработчики, которые открывают транзакции сами (см. `register`).
_OWN_TRANSACTION: set[str] = set()


def register(
    event_type: str, *, manages_own_transaction: bool = False
) -> Callable[[EventHandler], EventHandler]:
    """Зарегистрировать обработчик события.

    По умолчанию обработчик выполняется целиком в одной транзакции: так у него
    есть RLS-контекст и атомарность, и думать об этом не нужно. Обработчику,
    который ходит наружу — к модели, в мессенджер, — такая транзакция стоит
    соединения из пула на всё время ожидания. Он выставляет
    `manages_own_transaction` и открывает `tenant_atomic` сам, вокруг обращений
    к базе. Забытый блок не опасен: без транзакции RLS-настройка пуста и строки
    просто не видны — ошибка проявится сразу.
    """

    def decorator(handler: EventHandler) -> EventHandler:
        _REGISTRY[event_type] = handler
        if manages_own_transaction:
            _OWN_TRANSACTION.add(event_type)
        return handler

    return decorator


def dispatch(event: OutboxEvent) -> None:
    handler = _REGISTRY.get(event.event_type)
    if handler is None:
        logger.info("No handler registered for event %s", event.event_type)
        return
    context = tenant_context_for_event(event)
    if context is None:
        handler(event.payload, None)
        return
    if event.event_type in _OWN_TRANSACTION:
        handler(event.payload, context)
        return
    with tenant_atomic(context):
        handler(event.payload, context)
