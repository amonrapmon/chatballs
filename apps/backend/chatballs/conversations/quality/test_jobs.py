from uuid import uuid4

from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from chatballs.conversations.models import LifecycleState, MessageAuthor, SystemEvent
from chatballs.identity.models import EmployeeRole
from chatballs.tenancy.context import TenantContext
from chatballs.testing import system_tenant_context

from .criteria import configure_quality
from .jobs import finish_quality_job, request_quality_job, start_quality_job
from .models import QualityJob, QualityJobState
from .test_base import QualityTestBase


class JobTests(QualityTestBase):
    def test_snapshot_contains_only_public_messages_before_completion(self):
        settings = self.configure()
        public = [self.message(), self.message(author_type=MessageAuthor.OPERATOR, text="Reply"),
                  self.message(author_type=MessageAuthor.AI, transcript="Voice", text="")]
        self.message(author_type=MessageAuthor.SYSTEM, text="Private transfer reason")
        self.message(author_type=MessageAuthor.OPERATOR, system_event=SystemEvent.TOOL_CALLED, text="Internal")
        completed_at = timezone.now()
        later = self.message(text="After completion")
        job = self.job(completed_at=completed_at)
        self.assertEqual([item["id"] for item in job.history_snapshot], [message.pk for message in public])
        self.assertNotIn(later.pk, [item["id"] for item in job.history_snapshot])
        self.assertEqual(job.completed_at, completed_at)
        self.assertEqual(job.criteria_version_id, settings.current_version_id)
        self.assertEqual(len(job.history_revision), 64)
        original = job.history_snapshot
        public[0].text = "Changed"
        public[0].save(update_fields=["text"])
        job.refresh_from_db()
        self.assertEqual(job.history_snapshot, original)

    def test_redelivery_is_idempotent_and_explicit_repeat_is_new_revision(self):
        self.configure()
        message = self.message()
        args = {"context": self.context, "conversation_id": self.conversation.pk,
                "completion_event_id": uuid4(), "completed_at": timezone.now(), "operation_id": uuid4()}
        first = request_quality_job(**args)
        alias_args = {**args, "operation_id": uuid4()}
        self.assertEqual(request_quality_job(**alias_args).pk, first.pk)
        configure_quality(context=self.context, enabled=True, criteria=[{"code": "new", "description": "New", "scale": [0, 1]}])
        message.text = "Edited"
        message.save(update_fields=["text"])
        self.assertEqual(request_quality_job(**args).pk, first.pk)
        self.assertEqual(request_quality_job(**alias_args).pk, first.pk)
        repeat_args = {**args, "operation_id": uuid4(), "repeat": True}
        repeated = request_quality_job(**repeat_args)
        self.assertEqual(request_quality_job(**repeat_args).pk, repeated.pk)
        self.assertEqual(repeated.revision, 2)
        self.assertNotEqual(repeated.history_revision, first.history_revision)
        self.assertNotEqual(repeated.criteria_version_id, first.criteria_version_id)
        self.assertEqual(QualityJob.objects.count(), 2)
        self.assertEqual(self.job().revision, 1)  # A different completion event.

    def test_lifecycle_completion_and_operation_conflicts_are_rejected(self):
        self.configure()
        first = self.job()
        with self.assertRaises(ValidationError):
            self.job(operation_id=first.operation_id)
        with self.assertRaises(ValidationError):
            self.job(completion_event_id=first.completion_event_id, completed_at=timezone.now())
        with self.assertRaises(ValidationError):
            self.job(completed_at=self.conversation.created_at.replace(tzinfo=None))
        with self.assertRaises(ValidationError):
            self.job(completed_at="2026-10-08")
        self.conversation.lifecycle = LifecycleState.OPEN
        self.conversation.save(update_fields=["lifecycle"])
        with self.assertRaises(ValidationError):
            self.job()

    def test_job_transitions_and_duplicate_worker_completion_keep_original(self):
        self.configure()
        job = self.job()
        worker = system_tenant_context(self.organization)
        self.assertEqual(job.state, QualityJobState.WAITING)
        with self.assertRaises(ValidationError):
            finish_quality_job(context=worker, job_id=job.pk, validated_result={"score": 1})
        self.assertTrue(start_quality_job(context=worker, job_id=job.pk))
        self.assertFalse(start_quality_job(context=worker, job_id=job.pk))
        finish_quality_job(context=worker, job_id=job.pk, validated_result={"score": 1})
        finish_quality_job(context=worker, job_id=job.pk, validated_result={"score": 2})
        job.refresh_from_db()
        self.assertEqual(job.state, QualityJobState.SUCCEEDED)
        self.assertEqual(job.result.data, {"score": 1})
        self.assertIsNotNone(job.started_at)
        self.assertGreaterEqual(job.finished_at, job.started_at)
        failed = self.job()
        start_quality_job(context=worker, job_id=failed.pk)
        finish_quality_job(context=worker, job_id=failed.pk, error_code="provider_unavailable")
        failed.refresh_from_db()
        self.assertEqual(failed.state, QualityJobState.FAILED)
        self.assertEqual(failed.error_code, "provider_unavailable")
        self.assertFalse(hasattr(failed, "result"))

    def test_services_reject_other_tenant_and_ordinary_employee(self):
        self.configure()
        with self.assertRaises(NotFound):
            self.job(conversation_id=self.foreign_conversation.pk)
        job = self.job()
        with self.assertRaises(NotFound):
            start_quality_job(context=system_tenant_context(self.foreign), job_id=job.pk)
        employee = TenantContext.for_membership(self.members[EmployeeRole.EMPLOYEE])
        with self.assertRaises(PermissionDenied):
            self.job(context=employee)
        with self.assertRaises(PermissionDenied):
            start_quality_job(context=employee, job_id=job.pk)
