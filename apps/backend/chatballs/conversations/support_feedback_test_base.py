"""Focused integration setup using project services in PostgreSQL's test DB."""

from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from chatballs.conversations.domain_event_models import ConversationEventHistoryStart
from chatballs.conversations.domain_events import record_fact
from chatballs.conversations.models import Message
from chatballs.conversations.quality.criteria import configure_quality
from chatballs.conversations.quality.jobs import finish_quality_job, start_quality_job
from chatballs.conversations.quality.models import QualityJob
from chatballs.conversations.support_filters import ReportFilters
from chatballs.conversations.support_report import calculate_support_report
from chatballs.identity.models import HumanUser, OrganizationMembership
from chatballs.ratings.credentials import credential_for
from chatballs.ratings.models import RatingRequest
from chatballs.ratings.test_support import RatingTestBase
from chatballs.ratings.web_delivery import deliver_due_requests
from chatballs.testing import TenantAPIClient

CRITERIA = [{"code": "resolution", "description": "Resolution", "scale": [0, 1, 2]}]


class FeedbackTestBase(RatingTestBase):
    @classmethod
    def setUpTestData(cls):
        ConversationEventHistoryStart.objects.get_or_create(pk=1)
        super().setUpTestData()

    def setUp(self):
        super().setUp()
        self.start = self.conversation.created_at
        self.end = timezone.now() + timedelta(hours=1)
        self.filters = ReportFilters(self.start, self.end, "UTC")
        self.colleague = OrganizationMembership.objects.create(
            organization=self.organization, role="EMPLOYEE",
            user=HumanUser.objects.create_user(email="feedback-colleague@test.invalid"),
        )
        self.idle = OrganizationMembership.objects.create(
            organization=self.organization, role="EMPLOYEE",
            user=HumanUser.objects.create_user(email="feedback-idle@test.invalid"),
        )
        configure_quality(context=self.context, enabled=True, criteria=CRITERIA)
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/api/v1/organizations/{self.organization.public_id}/conversations/support-report/"
        self.params = {key: value for key, value in self.filters.payload().items() if value is not None}

    def reply(self, user=None, conversation=None, **changes):
        return Message.objects.create(
            conversation=conversation or self.conversation, author_type="OPERATOR",
            author_user=user or self.user, text="Public reply", **changes,
        )

    def complete(self, conversation=None):
        conversation = conversation or self.conversation
        conversation.lifecycle = "CLOSED"
        conversation.save(update_fields=["lifecycle"])
        return record_fact(conversation, "CLOSED", actor_kind="HUMAN", initiated_by_id=self.idle.user_id)

    def rated(self, event, value=5, comment=""):
        target = RatingRequest.objects.get(completion=event)
        deliver_due_requests(self.context)
        public = APIClient()
        public.credentials(HTTP_AUTHORIZATION=f"Bearer {credential_for(target)}")
        response = public.post("/api/v1/ratings/", {"value": value, "comment": comment}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return target.result

    def analyzed(self, event, value=1):
        job = QualityJob.objects.get(completion_event_id=event.operation_id)
        self.finish(job, value)
        return job

    def finish(self, job, value):
        start_quality_job(context=self.context, job_id=job.pk)
        finish_quality_job(context=self.context, job_id=job.pk, validated_result={"conclusions": [{
            "code": "resolution", "value": value, "explanation": "Reviewed", "recommendations": [],
            "messageIds": [job.history_snapshot[0]["id"]],
        }]})

    def report(self, **changes):
        return calculate_support_report(context=self.context, filters=ReportFilters(
            self.start, self.end, "UTC", **changes,
        ))
