import logging
from collections.abc import Callable
from dataclasses import dataclass

from chatballs.events.models import OutboxEvent
from chatballs.events.services import tenant_context_for_event
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic

logger = logging.getLogger(__name__)

EventHandler = Callable[[dict, TenantContext | None], None]


@dataclass(frozen=True)
class HandlerRegistration:
    handler: EventHandler
    tenant_transaction: bool = True
    recover_stale_processing: bool = False


_REGISTRY: dict[str, HandlerRegistration] = {}


def register(
    event_type: str,
    *,
    tenant_transaction: bool = True,
    recover_stale_processing: bool = False,
) -> Callable[[EventHandler], EventHandler]:
    def decorator(handler: EventHandler) -> EventHandler:
        _REGISTRY[event_type] = HandlerRegistration(
            handler=handler,
            tenant_transaction=tenant_transaction,
            recover_stale_processing=recover_stale_processing,
        )
        return handler

    return decorator


def get_registration(event_type: str) -> HandlerRegistration | None:
    return _REGISTRY.get(event_type)


def recoverable_event_types() -> tuple[str, ...]:
    return tuple(
        event_type
        for event_type, registration in _REGISTRY.items()
        if registration.recover_stale_processing
    )


def dispatch(event: OutboxEvent) -> None:
    registration = get_registration(event.event_type)
    if registration is None:
        logger.info("No handler registered for event %s", event.event_type)
        return
    context = tenant_context_for_event(event)
    if context is None:
        registration.handler(event.payload, None)
        return
    if not registration.tenant_transaction:
        registration.handler(event.payload, context)
        return
    with tenant_atomic(context):
        registration.handler(event.payload, context)
