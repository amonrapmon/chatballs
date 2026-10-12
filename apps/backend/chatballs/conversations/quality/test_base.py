from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from chatballs.channels.models import Channel
from chatballs.conversations.models import (
    Contact,
    Conversation,
    LifecycleState,
    Message,
    MessageAuthor,
)
from chatballs.identity.models import EmployeeRole, HumanUser, Organization, OrganizationMembership
from chatballs.tenancy.context import TenantContext

from .criteria import configure_quality
from .jobs import finish_quality_job, request_quality_job, start_quality_job

CRITERIA = [{"code": "resolution", "description": "Was the question resolved?", "scale": [0, 1, 2]}]


class QualityTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(name="Quality", slug="quality")
        cls.foreign = Organization.objects.create(name="Foreign quality", slug="foreign-quality")
        cls.members = {}
        for role in EmployeeRole.values:
            user = HumanUser.objects.create_user(email=f"{role}@quality.test")
            cls.members[role] = OrganizationMembership.objects.create(
                organization=cls.organization, user=user, role=role,
            )
        cls.foreign_member = OrganizationMembership.objects.create(
            organization=cls.foreign, user=HumanUser.objects.create_user(email="foreign@quality.test"),
            role=EmployeeRole.OWNER,
        )
        cls.context = TenantContext.for_membership(cls.members[EmployeeRole.OWNER])
        cls.foreign_context = TenantContext.for_membership(cls.foreign_member)
        cls.conversation = Conversation.objects.create(
            organization=cls.organization, lifecycle=LifecycleState.CLOSED,
            channel=Channel.objects.create(organization=cls.organization, name="Quality", code="quality"),
            contact=Contact.objects.create(organization=cls.organization, name="Customer"),
        )
        cls.foreign_conversation = Conversation.objects.create(
            organization=cls.foreign, lifecycle=LifecycleState.CLOSED,
            channel=Channel.objects.create(organization=cls.foreign, name="Quality", code="quality"),
            contact=Contact.objects.create(organization=cls.foreign, name="Customer"),
        )

    def configure(self, **changes):
        return configure_quality(**{"context": self.context, "enabled": True, "criteria": CRITERIA, **changes})

    def job(self, **changes):
        return request_quality_job(**{
            "context": self.context, "conversation_id": self.conversation.pk,
            "completion_event_id": uuid4(), "completed_at": timezone.now(),
            "operation_id": uuid4(), **changes,
        })

    def result(self):
        self.configure()
        job = self.job()
        start_quality_job(context=self.context, job_id=job.pk)
        finish_quality_job(context=self.context, job_id=job.pk, validated_result={"resolution": 1})
        return job.result

    def message(self, **changes):
        return Message.objects.create(**{
            "conversation": self.conversation, "author_type": MessageAuthor.CONTACT,
            "text": "Question", **changes,
        })
