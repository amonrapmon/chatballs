from datetime import timedelta
from unittest import mock

from django.test import TransactionTestCase
from django.utils import timezone

from chatballs.events.models import OutboxEvent, OutboxStatus
from chatballs.events.services import PROCESSING_LEASE_SECONDS, claim_next_outbox_event


class OutboxClaimTests(TransactionTestCase):
    databases = {"default", "platform"}
    reset_sequences = True

    def setUp(self) -> None:
        patch = mock.patch("chatballs.events.services.OUTBOX_DB", "default")
        patch.start()
        self.addCleanup(patch.stop)

    def _event(self, *, event_type: str, status: str, next_attempt_at):
        return OutboxEvent.objects.create(
            aggregate_type="Test",
            aggregate_id=event_type,
            event_type=event_type,
            payload={},
            status=status,
            next_attempt_at=next_attempt_at,
        )

    def test_gateway_claim_sets_processing_lease(self) -> None:
        before = timezone.now()
        event = self._event(
            event_type="gateway.delivery_command.requested.v1",
            status=OutboxStatus.PENDING,
            next_attempt_at=before - timedelta(seconds=1),
        )

        claimed = claim_next_outbox_event()

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.id, event.id)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.PROCESSING)
        self.assertGreaterEqual(
            event.next_attempt_at,
            before + timedelta(seconds=PROCESSING_LEASE_SECONDS - 1),
        )

    def test_expired_gateway_processing_event_is_not_claimed_without_global_recovery(self) -> None:
        event = self._event(
            event_type="gateway.delivery_command.requested.v1",
            status=OutboxStatus.PROCESSING,
            next_attempt_at=timezone.now() - timedelta(seconds=1),
        )

        claimed = claim_next_outbox_event()

        self.assertIsNone(claimed)
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.PROCESSING)

    def test_non_expired_gateway_processing_event_is_not_reclaimable(self) -> None:
        event = self._event(
            event_type="gateway.delivery_command.requested.v1",
            status=OutboxStatus.PROCESSING,
            next_attempt_at=timezone.now() + timedelta(seconds=60),
        )

        self.assertIsNone(claim_next_outbox_event())
        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.PROCESSING)

    def test_pending_and_failed_events_keep_existing_claim_behavior(self) -> None:
        failed = self._event(
            event_type="tests.failed",
            status=OutboxStatus.FAILED,
            next_attempt_at=timezone.now() - timedelta(seconds=1),
        )

        claimed = claim_next_outbox_event()

        self.assertIsNotNone(claimed)
        self.assertEqual(claimed.id, failed.id)
