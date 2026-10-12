from datetime import timedelta

from django.db import DatabaseError, connection
from django.test import TransactionTestCase
from django.utils import timezone

from chatballs.ai.assistance_test_base import AssistanceTestData
from chatballs.ai.models import (
    ReplyAssistanceAttempt,
    ReplyAssistanceStatus,
    ReplySuggestion,
)
from chatballs.tenancy.database import tenant_atomic


class AssistanceRuntimeRoleTests(AssistanceTestData, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.other, self.other_member, self.other_agent, self.other_conversation = self.create_tenant(
            "assist-other"
        )

    def as_app(self, organization, callback):
        with tenant_atomic(organization.id):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            return callback()

    def test_own_runtime_can_store_complete_and_reject_and_foreign_reads_nothing(self):
        attempt = self.as_app(self.organization, self.attempt)
        suggestion = self.as_app(self.organization, lambda: self.suggestion(attempt))
        self.as_app(self.organization, lambda: ReplySuggestion.objects.filter(pk=suggestion.pk).update(
            status=ReplyAssistanceStatus.RUNNING, started_at=timezone.now(),
        ))
        self.as_app(self.organization, lambda: ReplySuggestion.objects.filter(pk=suggestion.pk).update(
            status=ReplyAssistanceStatus.READY, completed_at=timezone.now(), original_text="Source",
        ))
        self.as_app(self.organization, lambda: ReplySuggestion.objects.filter(pk=suggestion.pk).update(
            rejected_by=self.member, rejected_at=timezone.now(),
        ))
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.original_text, "Source")
        self.assertEqual(suggestion.rejected_by, self.member)
        with self.assertRaises(DatabaseError):
            self.as_app(self.organization, lambda: ReplySuggestion.objects.filter(pk=suggestion.pk).update(
                original_text="Edited source",
            ))
        own = self.as_app(self.organization, lambda: (
            ReplyAssistanceAttempt.objects.count(), ReplySuggestion.objects.count(),
        ))
        foreign = self.as_app(self.other, lambda: (
            ReplyAssistanceAttempt.objects.count(), ReplySuggestion.objects.count(),
        ))
        self.assertEqual(own, (1, 1))
        self.assertEqual(foreign, (0, 0))
        self.assertEqual(self.as_app(self.other, lambda: ReplySuggestion.objects.filter(
            pk=suggestion.pk
        ).update(original_text="Foreign edit")), 0)
        # FORCE RLS действует и без установленного tenant-контекста.
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE chatballs_runtime_app")
        try:
            self.assertFalse(ReplyAssistanceAttempt.objects.exists())
            self.assertFalse(ReplySuggestion.objects.exists())
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def test_bulk_insert_cannot_bypass_tenant_relations_or_rls(self):
        attempt = self.attempt()
        foreign_attempt = self.attempt(
            organization=self.other, requested_by=self.other_member, agent=self.other_agent,
            conversation=self.other_conversation,
        )
        attempt_values = {
            "organization": self.organization, "conversation": self.conversation,
            "agent": self.agent, "requested_by": self.member,
            "operation_key": "forged", "history_version": "v1",
        }
        suggestion_values = {
            "organization": self.organization, "attempt": attempt, "requested_by": self.member,
            "operation_key": "forged", "history_version": "v1", "position": 1,
        }
        ready_time = timezone.now() + timedelta(minutes=1)
        rows = [
            *[ReplyAssistanceAttempt(**{**attempt_values, **values}) for values in (
                {"organization": self.other}, {"conversation": self.other_conversation},
                {"agent": self.other_agent}, {"requested_by": self.other_member},
            )],
            *[ReplySuggestion(**{**suggestion_values, **values}) for values in (
                {"organization": self.other}, {"attempt": foreign_attempt},
                {"requested_by": self.other_member},
                {"rejected_by": self.other_member, "rejected_at": ready_time,
                 "status": ReplyAssistanceStatus.READY, "started_at": ready_time,
                 "completed_at": ready_time, "original_text": "Forged"},
            )],
        ]
        for row in rows:
            with self.subTest(model=type(row).__name__, values=row.__dict__):
                with self.assertRaises(DatabaseError) as error:
                    self.as_app(self.organization, lambda row=row: type(row).objects.bulk_create([row]))
                self.assertTrue(
                    "cross-tenant relation" in str(error.exception)
                    or "row-level security" in str(error.exception), str(error.exception),
                )
        self.assertEqual(ReplyAssistanceAttempt.objects.count(), 2)
        self.assertFalse(ReplySuggestion.objects.exists())
