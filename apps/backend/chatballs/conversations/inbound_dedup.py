"""Mailbox/provider-scoped inbox deduplication using PostgreSQL uniqueness."""

import hashlib

from django.db import IntegrityError, transaction

from chatballs.events.models import EventOwnership, InboxEvent
from chatballs.tenancy.context import TenantContext


def _already_processed(\n    context: TenantContext, source: str, external_id: str, text: str,\n    *, payload_hash: str | None = None,\n) -> bool:
    """Отметить сообщение обработанным; True — оно уже приходило.

    Вставка идёт своей точкой сохранения. Вызывают эту функцию изнутри
    транзакции (воркер держит ``tenant_atomic`` на весь цикл поллинга), а
    IntegrityError в Postgres обрывает транзакцию целиком: без savepoint
    первый же повтор сообщения ронял не дедупликацию, а весь цикл — со всеми
    остальными подключениями организации.
    """
    payload_hash = payload_hash or hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
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
        if len(payload_hash) == 64:
            # Connector v1 fingerprints the WHOLE normalized event, not just text.
            # Replay with a modified attachment/identity/body is a conflict.
            existing = InboxEvent.objects.get(source=source, external_event_id=external_id)
            if existing.payload_hash != payload_hash:
                raise ValueError("connector_event_id_conflict") from None
        return True
