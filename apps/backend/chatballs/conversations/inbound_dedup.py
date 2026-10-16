"""Mailbox/provider-scoped inbox deduplication using PostgreSQL uniqueness."""

import hashlib

from django.db import IntegrityError, transaction

from chatballs.events.models import EventOwnership, InboxEvent
from chatballs.tenancy.context import TenantContext


def _already_processed(context: TenantContext, source: str, external_id: str, text: str) -> bool:
    """Отметить сообщение обработанным; True — оно уже приходило.

    Вставка идёт своей точкой сохранения. Вызывают эту функцию изнутри
    транзакции (воркер держит ``tenant_atomic`` на весь цикл поллинга), а
    IntegrityError в Postgres обрывает транзакцию целиком: без savepoint
    первый же повтор сообщения ронял не дедупликацию, а весь цикл — со всеми
    остальными подключениями организации.
    """
    payload_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
    try:
        with transaction.atomic():
            InboxEvent.objects.create(
                source=source,
                external_event_id=external_id,
                payload_hash=payload_hash,
                ownership=EventOwnership.TENANT,
                organization=context.organization,
            )
        return False
    except IntegrityError:
        return True
