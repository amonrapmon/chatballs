from uuid import uuid4

from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.models import Contact, Conversation
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import HumanUser, Organization, OrganizationMembership
from chatballs.integrations.models import Integration
from chatballs.tenancy.context import TenantContext


class DomainEventTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(name="Facts", slug="facts")
        cls.foreign = Organization.objects.create(name="Other facts", slug="other-facts")
        for prefix, organization in (("", cls.organization), ("foreign_", cls.foreign)):
            user = HumanUser.objects.create_user(email=f"{prefix}member@facts.test")
            member = OrganizationMembership.objects.create(
                organization=organization, user=user, role="OWNER"
            )
            group = EmployeeGroup.objects.create(organization=organization, name="Support")
            channel = Channel.objects.create(organization=organization, name="Facts", code="facts")
            contact = Contact.objects.create(organization=organization, name="Customer")
            connection = Integration.objects.create(
                organization=organization, kind="MESSENGER", provider="WEB", name="Web"
            )
            conversation = Conversation.objects.create(
                organization=organization, channel=channel, contact=contact,
                connection=connection, group=group, assigned_operator=user,
            )
            for name, value in (("user", user), ("member", member), ("group", group),
                                ("connection", connection), ("conversation", conversation)):
                setattr(cls, f"{prefix}{name}", value)
        cls.context = TenantContext.for_membership(cls.member)

    def row(self, **changes):
        return ConversationEvent(**{
            "organization_id": self.organization.pk,
            "conversation_id": self.conversation.pk,
            "event_type": "ACCEPTED", "actor_kind": "HUMAN", "operation_id": uuid4(),
            "initiated_by_id": self.user.pk, "responsible_id": self.user.pk,
            "group_id": self.group.pk, "connection_id": self.connection.pk, "transport": "WEB",
            **changes,
        })
