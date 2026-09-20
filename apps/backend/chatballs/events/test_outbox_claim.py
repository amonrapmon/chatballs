"""Очередь событий: порядок внутри агрегата и возврат зависших."""

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from chatballs.events.models import EventOwnership, OutboxEvent, OutboxStatus
from chatballs.events.services import claim_next_outbox_event, release_stale_processing
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.tenancy.context import TenantActorKind


class OutboxClaimTests(TestCase):
    """Захват событий.

    В проде outbox читает роль platform, в тестах отдельного соединения под неё
    нет — все алиасы смотрят в одну базу. Подменяется только алиас: сами
    запросы те же, что в проде.
    """

    def setUp(self) -> None:
        bootstrap_owner(email="owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        patch = mock.patch("chatballs.events.services.OUTBOX_DB", "default")
        patch.start()
        self.addCleanup(patch.stop)

    def _event(self, aggregate_id: str, event_type: str = "conversation.ai_turn_requested"):
        return OutboxEvent.objects.create(
            aggregate_type="Conversation",
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload={},
            ownership=EventOwnership.TENANT,
            organization=self.organization,
            actor_kind=TenantActorKind.MACHINE,
        )

    def test_second_event_of_the_same_aggregate_waits(self) -> None:
        # Два ответа одному диалогу не считаются параллельно: иначе они
        # приезжают клиенту вперемешку.
        self._event("7")
        self._event("7")

        first = claim_next_outbox_event()
        self.assertIsNotNone(first)
        self.assertIsNone(claim_next_outbox_event())

    def test_other_aggregates_are_not_blocked(self) -> None:
        self._event("7")
        self._event("8")

        self.assertIsNotNone(claim_next_outbox_event())
        self.assertIsNotNone(claim_next_outbox_event())

    def test_stale_processing_returns_to_the_queue(self) -> None:
        # Процесс упал между взятием события и записью результата: без
        # возврата оно осталось бы в работе навсегда, а вместе с ним встал бы
        # весь диалог.
        event = self._event("7")
        claimed = claim_next_outbox_event()
        self.assertEqual(claimed.id, event.id)

        self.assertEqual(release_stale_processing(), 0)

        OutboxEvent.objects.filter(id=event.id).update(
            next_attempt_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(release_stale_processing(), 1)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.PENDING)
        self.assertIsNotNone(claim_next_outbox_event())
