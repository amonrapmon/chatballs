from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase
from django.utils import timezone

from chatballs.ai.assistance_models import ReplyAssistanceError
from chatballs.ai.assistance_test_base import AssistanceTestData
from chatballs.ai.models import (
    ReplyAssistanceAttempt,
    ReplyAssistanceStatus,
    ReplySuggestion,
)
from chatballs.conversations.models import Message
from chatballs.events.models import OutboxEvent


class AssistanceStorageTests(AssistanceTestData, TestCase):
    def ready(self, operation, **values):
        operation.status = ReplyAssistanceStatus.RUNNING
        operation.started_at = timezone.now()
        operation.save()
        operation.status = ReplyAssistanceStatus.READY
        operation.completed_at = timezone.now()
        for key, value in values.items():
            setattr(operation, key, value)
        operation.save()

    def test_alternative_and_rejection_preserve_original_and_dialogue(self):
        before = (self.conversation.control_mode, self.conversation.assigned_operator_id,
                  self.conversation.expected_responder, self.conversation.last_activity_at)
        counts = (Message.objects.count(), OutboxEvent.objects.count())
        attempt = self.attempt()
        original = self.suggestion(attempt)
        self.ready(original, original_text="Original suggestion")
        self.ready(attempt)
        original.rejected_by = self.member
        original.rejected_at = timezone.now()
        original.save(update_fields=["rejected_by", "rejected_at"])
        alternative = self.suggestion(
            attempt, operation_key="alternative", position=2, history_version="history-v2",
        )
        self.ready(alternative, original_text="Alternative suggestion")
        original.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(list(attempt.suggestions.values_list("original_text", flat=True)),
                         ["Original suggestion", "Alternative suggestion"])
        self.assertEqual((original.requested_by, original.history_version),
                         (self.member, "history-v1"))
        self.assertEqual((alternative.requested_by, alternative.history_version),
                         (self.member, "history-v2"))
        self.assertEqual((attempt.requested_by, attempt.history_version), (self.member, "history-v1"))
        self.assertEqual(original.rejected_by, self.member)
        self.assertIsNotNone(original.rejected_at)
        self.assertLessEqual(original.created_at, original.started_at)
        self.assertLessEqual(original.started_at, original.completed_at)
        self.assertEqual(original.status, ReplyAssistanceStatus.READY)
        self.assertEqual(attempt.status, ReplyAssistanceStatus.READY)
        self.conversation.refresh_from_db()
        self.assertEqual(before, (self.conversation.control_mode, self.conversation.assigned_operator_id,
                                  self.conversation.expected_responder, self.conversation.last_activity_at))
        self.assertEqual(counts, (Message.objects.count(), OutboxEvent.objects.count()))

    def test_database_prevents_overwrite_reassociation_and_repeated_operation(self):
        attempt = self.attempt()
        suggestion = self.suggestion(attempt)
        self.ready(suggestion, original_text="Immutable source")
        suggestion.rejected_by = self.member
        suggestion.rejected_at = timezone.now()
        suggestion.save()
        other_attempt = self.attempt(operation_key="second")
        for values in (
            {"original_text": "edited"}, {"history_version": "changed"},
            {"operation_key": "changed"}, {"attempt": other_attempt},
            {"status": ReplyAssistanceStatus.PENDING, "started_at": None,
             "completed_at": None, "original_text": ""},
            {"rejected_by": None, "rejected_at": None},
        ):
            with self.subTest(values=values), self.assertRaises(DatabaseError), transaction.atomic():
                ReplySuggestion.objects.filter(pk=suggestion.pk).update(**values)
        for insert in (
            lambda: self.attempt(),
            lambda: self.suggestion(attempt, position=2),
            lambda: self.suggestion(attempt, operation_key="new"),
            lambda: self.suggestion(other_attempt, operation_key="original"),
        ):
            with self.assertRaises(DatabaseError), transaction.atomic():
                insert()
        self.assertEqual(ReplySuggestion.objects.count(), 1)
        self.assertEqual(ReplyAssistanceAttempt.objects.count(), 2)
        for values in ({"history_version": "changed"}, {"requested_by": None},
                       {"operation_key": "changed"}, {"created_at": timezone.now()}):
            with self.subTest(values=values), self.assertRaises(DatabaseError), transaction.atomic():
                ReplyAssistanceAttempt.objects.filter(pk=attempt.pk).update(**values)
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.original_text, "Immutable source")

    def test_state_and_safe_error_constraints(self):
        attempt = self.attempt()
        self.assertEqual(attempt.status, ReplyAssistanceStatus.PENDING)
        for values in (
            {"status": "UNKNOWN"}, {"status": ReplyAssistanceStatus.RUNNING},
            {"status": ReplyAssistanceStatus.READY, "completed_at": timezone.now()},
            {"status": ReplyAssistanceStatus.ERROR, "completed_at": timezone.now(),
             "error_code": "provider response with a secret"},
        ):
            with self.subTest(values=values), self.assertRaises(DatabaseError), transaction.atomic():
                ReplyAssistanceAttempt.objects.filter(pk=attempt.pk).update(**values)
        attempt.status = ReplyAssistanceStatus.ERROR
        attempt.completed_at = timezone.now()
        attempt.error_code = ReplyAssistanceError.GENERATION_FAILED
        attempt.save()
        with self.assertRaises(DatabaseError), transaction.atomic():
            ReplyAssistanceAttempt.objects.filter(pk=attempt.pk).update(
                status=ReplyAssistanceStatus.PENDING, completed_at=None, error_code="",
            )
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, "HUMAN")
        self.assertEqual(self.conversation.assigned_operator, self.member.user)
        self.assertFalse(Message.objects.exists())
        self.assertFalse(OutboxEvent.objects.exists())

    def test_model_rejects_foreign_relations(self):
        other, member, agent, conversation = self.create_tenant("assist-other")
        for values in ({"agent": agent}, {"conversation": conversation}, {"requested_by": member}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.attempt(**values)
        attempt = self.attempt()
        for values in ({"requested_by": member}, {"organization": other}, {"rejected_by": member}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                self.suggestion(attempt, **values)
