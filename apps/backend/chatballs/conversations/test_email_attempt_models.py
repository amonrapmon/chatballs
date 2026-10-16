from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.utils import timezone

from chatballs.conversations.email_attempt_models import (
    EmailAttemptState,
    EmailSendAttempt,
)
from chatballs.conversations.email_continuation_test_base import (
    EmailContinuationTestBase,
)
from chatballs.events.models import OutboxEvent


class EmailAttemptModelTests(EmailContinuationTestBase):
    def test_attempt_history_distinguishes_smtp_acceptance_error_and_unknown(self):
        operation = self.operation()
        first = self.attempt(operation)
        first.save()
        self.assertEqual(first.state, EmailAttemptState.PENDING)
        first.started_at = timezone.now()
        first.state = EmailAttemptState.SENDING
        first.save()
        first.refresh_from_db()
        self.assertEqual(first.state, EmailAttemptState.SENDING)
        first.state = EmailAttemptState.UNKNOWN
        first.error_code = "WORKER_INTERRUPTED"
        first.finished_at = timezone.now()
        first.save()
        second = self.attempt(operation, 2)
        second.save()
        second.state = EmailAttemptState.FAILED
        second.error_code = "CONNECTION_UNAVAILABLE"
        second.finished_at = timezone.now()
        second.save()
        third = self.attempt(operation, 3)
        third.save()
        third.started_at = timezone.now()
        third.finished_at = timezone.now()
        third.state = EmailAttemptState.SMTP_ACCEPTED
        third.save()
        self.assertEqual(list(operation.attempts.values_list("number", "state")), [
            (1, "UNKNOWN"), (2, "FAILED"), (3, "SMTP_ACCEPTED"),
        ])
        self.assertEqual(EmailSendAttempt.objects.count(), 3)
        self.assertNotIn("DELIVERED", EmailAttemptState.values)
        for attempt in operation.attempts.all():
            self.assertEqual(attempt.initiated_by_id, self.member.pk)
            self.assertEqual(attempt.outbox_event.organization_id, self.organization.pk)
            self.assertEqual(attempt.operation.letter.connection_id, self.mailbox.pk)
            self.assertIsNotNone(attempt.created_at)
            self.assertIsNotNone(attempt.finished_at)

    def test_database_rejects_fictitious_states_unsanitized_errors_and_inconsistent_times(self):
        attempt = self.attempt(self.operation())
        attempt.save()
        now = timezone.now()
        for changes in (
            {"state": "DELIVERED"}, {"state": "SENDING"}, {"state": "SMTP_ACCEPTED"},
            {"state": "UNKNOWN", "finished_at": now, "error_code": "TRANSPORT_ERROR"},
            {"state": "FAILED", "finished_at": now},
            {"error_code": "password=secret"}, {"number": 0},
            {"state": "SENDING", "started_at": attempt.created_at - timedelta(seconds=1)},
            {"state": "FAILED", "finished_at": attempt.created_at - timedelta(seconds=1),
             "error_code": "SMTP_REJECTED"},
            {"state": "UNKNOWN", "started_at": now + timedelta(seconds=1), "finished_at": now,
             "error_code": "TRANSPORT_ERROR"},
        ):
            with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                EmailSendAttempt.objects.filter(pk=attempt.pk).update(**changes)

    def test_retry_number_and_outbox_event_cannot_be_reused(self):
        operation = self.operation()
        first = self.attempt(operation)
        first.save()
        with self.assertRaises(DatabaseError), transaction.atomic():
            self.attempt(operation).save()
        with self.assertRaises(DatabaseError), transaction.atomic():
            self.attempt(operation, 2, outbox_event=first.outbox_event).save()

    def test_attempt_rejects_platform_outbox_and_foreign_initiator(self):
        operation = self.operation()
        platform_event = OutboxEvent.objects.create(
            aggregate_type="platform", aggregate_id="1", event_type="platform.noop",
        )
        with self.assertRaises(ValidationError):
            self.attempt(operation, outbox_event=platform_event).save()
        with self.assertRaises(ValidationError):
            self.attempt(operation, initiated_by=self.foreign_member).save()
