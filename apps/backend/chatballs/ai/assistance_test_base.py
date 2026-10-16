from chatballs.ai.models import AIAgent, ReplyAssistanceAttempt, ReplySuggestion
from chatballs.channels.models import Channel
from chatballs.conversations.models import Contact, Conversation
from chatballs.identity.models import (
    EmployeeRole,
    HumanUser,
    Organization,
    OrganizationMembership,
)


class AssistanceTestData:
    """Данные только изолированной тестовой БД; без seed и внешнего AI."""

    def create_tenant(self, slug):
        organization = Organization.objects.create(name=slug, slug=slug)
        user = HumanUser.objects.create_user(email=f"{slug}@example.test")
        membership = OrganizationMembership.objects.create(
            organization=organization, user=user, role=EmployeeRole.OWNER,
            position_title="Owner",
        )
        channel = Channel.objects.create(organization=organization, code=slug, name=slug)
        agent = AIAgent.objects.create(channel=channel, name=slug)
        contact = Contact.objects.create(organization=organization, name=slug)
        conversation = Conversation.objects.create(
            organization=organization, channel=channel, contact=contact,
            control_mode="HUMAN", expected_responder="OPERATOR", assigned_operator=user,
        )
        return organization, membership, agent, conversation

    def setUp(self):
        super().setUp()
        self.organization, self.member, self.agent, self.conversation = self.create_tenant("assist")

    def attempt(self, **overrides):
        values = {
            "organization": self.organization, "requested_by": self.member,
            "agent": self.agent, "conversation": self.conversation,
            "operation_key": "initial", "history_version": "history-v1",
        }
        values.update(overrides)
        return ReplyAssistanceAttempt.objects.create(**values)

    def suggestion(self, attempt, **overrides):
        values = {
            "attempt": attempt, "requested_by": self.member,
            "operation_key": "original", "history_version": "history-v1", "position": 1,
        }
        values.update(overrides)
        return ReplySuggestion.objects.create(**values)
