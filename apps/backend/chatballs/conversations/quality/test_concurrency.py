from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from django.db import close_old_connections, connections
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from chatballs.channels.models import Channel
from chatballs.conversations.models import Contact, Conversation, LifecycleState
from chatballs.identity.models import EmployeeRole, HumanUser, Organization, OrganizationMembership
from chatballs.tenancy.context import TenantContext

from .corrections import append_quality_correction
from .criteria import configure_quality
from .jobs import finish_quality_job, request_quality_job, start_quality_job
from .models import QualityCorrection, QualityCriteriaVersion, QualityJob
from .test_base import CRITERIA


class ConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Concurrent quality", slug="concurrent-quality")
        self.membership = OrganizationMembership.objects.create(
            organization=self.organization,
            user=HumanUser.objects.create_user(email="concurrent@quality.test"), role=EmployeeRole.OWNER,
        )
        self.context = TenantContext.for_membership(self.membership)
        self.conversation = Conversation.objects.create(
            organization=self.organization, lifecycle=LifecycleState.CLOSED,
            channel=Channel.objects.create(organization=self.organization, name="Quality", code="quality"),
            contact=Contact.objects.create(organization=self.organization, name="Customer"),
        )

    def concurrently(self, operation):
        barrier = Barrier(2)

        def run():
            close_old_connections()
            try:
                membership = OrganizationMembership.objects.select_related("organization", "user").get(pk=self.membership.pk)
                context = TenantContext.for_membership(membership)
                barrier.wait(timeout=30)
                return operation(context)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            return [future.result(timeout=60) for future in futures]

    def test_concurrent_configuration_allocates_distinct_versions(self):
        versions = self.concurrently(lambda context: configure_quality(
            context=context, enabled=True, criteria=CRITERIA,
        ).current_version.version)
        self.assertEqual(sorted(versions), [1, 2])
        self.assertEqual(QualityCriteriaVersion.objects.count(), 2)

    def test_concurrent_workers_claim_a_single_analysis_once(self):
        configure_quality(context=self.context, enabled=True, criteria=CRITERIA)
        job = request_quality_job(
            context=self.context, conversation_id=self.conversation.pk,
            completion_event_id=uuid4(), completed_at=timezone.now(), operation_id=uuid4(),
        )
        claimed = self.concurrently(lambda context: start_quality_job(context=context, job_id=job.pk))
        self.assertEqual(sorted(claimed), [False, True])
        finish_quality_job(context=self.context, job_id=job.pk, validated_result={"resolution": 1})
        finish_quality_job(context=self.context, job_id=job.pk, validated_result={"resolution": 2})
        self.assertEqual(QualityJob.objects.count(), 1)
        self.assertEqual(job.result.data, {"resolution": 1})

    def test_concurrent_duplicate_request_and_correction_do_not_overwrite(self):
        configure_quality(context=self.context, enabled=True, criteria=CRITERIA)
        args = {"conversation_id": self.conversation.pk, "completion_event_id": uuid4(),
                "completed_at": timezone.now(), "operation_id": uuid4(), "repeat": True}
        ids = self.concurrently(lambda context: request_quality_job(context=context, **args).pk)
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(QualityJob.objects.count(), 1)
        start_quality_job(context=self.context, job_id=ids[0])
        finish_quality_job(context=self.context, job_id=ids[0], validated_result={"resolution": 1})
        result = QualityJob.objects.get(pk=ids[0]).result

        def correct(context):
            try:
                append_quality_correction(
                    context=context, result_id=result.pk, expected_revision=0,
                    criterion_code="resolution", value=2, reason="Concurrent review",
                )
                return "saved"
            except ValidationError:
                return "conflict"

        self.assertEqual(sorted(self.concurrently(correct)), ["conflict", "saved"])
        self.assertEqual(QualityCorrection.objects.count(), 1)
        result.refresh_from_db()
        self.assertEqual(result.data, {"resolution": 1})
