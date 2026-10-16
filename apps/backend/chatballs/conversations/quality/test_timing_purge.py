from datetime import timedelta

from django.db import DatabaseError, connection, transaction

from chatballs.conversations.deletion import delete_conversation
from chatballs.conversations.domain_event_models import ConversationEventHistoryStart
from chatballs.conversations.domain_events import record_fact, record_public_reply
from chatballs.conversations.models import Conversation, MessageAuthor
from chatballs.conversations.support_filters import ReportFilters
from chatballs.conversations.support_report import calculate_support_report
from chatballs.tenancy.database import tenant_atomic

from .corrections import append_quality_correction
from .jobs import finish_quality_job, start_quality_job
from .models import QualityCorrection, QualityJob, QualityJobOperation, QualityResult
from .test_base import QualityTestBase
from .timing import temporal_facts


class TimingPurgeTests(QualityTestBase):
    @classmethod
    def setUpTestData(cls):
        ConversationEventHistoryStart.objects.get_or_create(pk=1)
        super().setUpTestData()

    def closed_job(self):
        self.configure()
        self.message()
        queue = record_fact(self.conversation, "QUEUE_ENTERED")
        accepted = record_fact(self.conversation, "ACCEPTED", actor_kind="HUMAN",
                               responsible_id=self.context.actor_user.pk)
        reply = self.message(author_type=MessageAuthor.OPERATOR, author_user=self.context.actor_user)
        answered = record_public_reply(reply)
        completion = record_fact(self.conversation, "CLOSED", responsible_id=self.context.actor_user.pk)
        return QualityJob.objects.get(completion_event_id=completion.operation_id), queue, accepted, answered

    def test_temporal_facts_equal_shared_report_calculation_and_real_timestamps(self):
        ConversationEventHistoryStart.objects.get_or_create(pk=1)
        job, queue, accepted, answered = self.closed_job()
        facts = temporal_facts(job)
        self.assertEqual(facts["state"], "available")
        report = calculate_support_report(context=self.context, filters=ReportFilters(
            self.conversation.created_at, job.completed_at + timedelta(microseconds=1), "UTC"))
        self.assertEqual(facts["metrics"], report["totals"])
        self.assertEqual(facts["metrics"]["values"]["waiting"]["seconds"],
                         round((accepted.occurred_at - queue.occurred_at).total_seconds(), 6))
        self.assertEqual(facts["metrics"]["values"]["firstResponse"]["meanSeconds"],
                         round((answered.occurred_at - queue.occurred_at).total_seconds(), 6))

    def test_missing_historical_base_nulls_times_explicitly(self):
        job, _, _, _ = self.closed_job()
        Conversation.objects.filter(pk=self.conversation.pk).update(created_at=self.conversation.created_at - timedelta(days=365))
        job = QualityJob.objects.get(pk=job.pk)
        facts = temporal_facts(job)
        self.assertEqual(facts["state"], "missing_history")
        self.assertIsNone(facts["metrics"]["values"]["firstResponse"]["meanSeconds"])
        self.assertIsNone(facts["metrics"]["values"]["handling"]["seconds"])

    def test_runtime_physical_dialog_deletion_purges_immutable_subtree_only(self):
        job, _, _, _ = self.closed_job()
        start_quality_job(context=self.context, job_id=job.pk)
        finish_quality_job(context=self.context, job_id=job.pk, validated_result={"resolution": 1})
        result = job.result
        append_quality_correction(context=self.context, result_id=result.pk, expected_revision=0,
                                  criterion_code="resolution", value=2, reason="Reviewed")
        with tenant_atomic(self.context):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            with self.assertRaises(DatabaseError), transaction.atomic():
                QualityJob.objects.filter(pk=job.pk)._raw_delete("default")
            with self.assertRaises(DatabaseError), transaction.atomic():
                QualityResult.objects.filter(pk=result.pk)._raw_delete("default")
            delete_conversation(context=self.context, conversation=self.conversation)
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
        self.assertFalse(Conversation.objects.filter(pk=self.conversation.pk).exists())
        self.assertEqual(QualityJob.objects.count(), 0)
        self.assertEqual(QualityResult.objects.count(), 0)
        self.assertEqual(QualityJobOperation.objects.count(), 0)
        self.assertEqual(QualityCorrection.objects.count(), 0)
        self.assertTrue(Conversation.objects.filter(pk=self.foreign_conversation.pk).exists())
