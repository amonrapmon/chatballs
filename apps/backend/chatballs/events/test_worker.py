from datetime import timedelta
from unittest import mock

from django.test import TransactionTestCase
from django.utils import timezone

from chatballs.events.management.commands.run_worker import Command
from chatballs.events.models import OutboxEvent, OutboxStatus


class OutboxWorkerTests(TransactionTestCase):
    databases = {"default", "platform"}
    reset_sequences = True

    def setUp(self) -> None:
        outbox_db_patch = mock.patch("chatballs.events.services.OUTBOX_DB", "default")
        outbox_db_patch.start()
        self.addCleanup(outbox_db_patch.stop)
        worker_db_patch = mock.patch(
            "chatballs.events.management.commands.run_worker.OUTBOX_DB", "default"
        )
        worker_db_patch.start()
        self.addCleanup(worker_db_patch.stop)

    def _event(self) -> OutboxEvent:
        return OutboxEvent.objects.create(
            aggregate_type="Message",
            aggregate_id="message-1",
            event_type="gateway.delivery_command.requested.v1",
            payload={},
            next_attempt_at=timezone.now() - timedelta(seconds=1),
        )

    def _run_one_event(self, event: OutboxEvent, *, dispatch_side_effect=None) -> None:
        with (
            mock.patch(
                "chatballs.events.management.commands.run_worker.claim_next_outbox_event",
                side_effect=[event, None],
            ),
            mock.patch(
                "chatballs.events.management.commands.run_worker.dispatch",
                side_effect=dispatch_side_effect,
            ),
            mock.patch(
                "chatballs.events.management.commands.run_worker.time.monotonic",
                return_value=0,
            ),
            mock.patch(
                "chatballs.events.management.commands.run_worker.time.sleep",
                side_effect=StopIteration,
            ),
        ):
            with self.assertRaises(StopIteration):
                Command().handle(role="events")

    def test_successful_handler_marks_event_processed(self) -> None:
        event = self._event()

        self._run_one_event(event)

        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.PROCESSED)
        self.assertIsNotNone(event.processed_at)

    def test_gateway_failure_uses_existing_mark_retry_path(self) -> None:
        event = self._event()

        self._run_one_event(event, dispatch_side_effect=RuntimeError("gateway network failure"))

        event.refresh_from_db()
        self.assertEqual(event.status, OutboxStatus.FAILED)
        self.assertEqual(event.attempts, 1)
        self.assertEqual(event.last_error, "gateway network failure")
