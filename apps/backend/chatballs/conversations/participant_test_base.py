from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.models import Contact, Conversation
from chatballs.conversations.participant_models import ConversationParticipant
from chatballs.identity.models import EmployeeRole, HumanUser, Organization, OrganizationMembership
from chatballs.tenancy.context import TenantContext


class ParticipantTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(name="Participation", slug="participation")
        cls.foreign = Organization.objects.create(name="Foreign", slug="foreign-participation")
        cls.members = []
        for index in range(3):
            user = HumanUser.objects.create_user(email=f"member{index}@participation.test")
            cls.members.append(OrganizationMembership.objects.create(
                organization=cls.organization, user=user, role=EmployeeRole.EMPLOYEE,
            ))
        foreign_user = HumanUser.objects.create_user(email="foreign@participation.test")
        cls.foreign_member = OrganizationMembership.objects.create(
            organization=cls.foreign, user=foreign_user, role=EmployeeRole.EMPLOYEE,
        )
        channel = Channel.objects.create(organization=cls.organization, code="local", name="Local")
        foreign_channel = Channel.objects.create(organization=cls.foreign, code="foreign", name="Foreign")
        contact = Contact.objects.create(organization=cls.organization, name="Customer")
        foreign_contact = Contact.objects.create(organization=cls.foreign, name="Foreign customer")
        cls.conversation = Conversation.objects.create(
            organization=cls.organization, channel=channel, contact=contact,
            assigned_operator=cls.members[0].user,
        )
        cls.foreign_conversation = Conversation.objects.create(
            organization=cls.foreign, channel=foreign_channel, contact=foreign_contact,
        )
        cls.context = TenantContext.for_membership(cls.members[0])

    def row(self, **changes):
        row = ConversationParticipant(
            organization_id=self.organization.pk,
            conversation_id=self.conversation.pk,
            membership_id=self.members[1].pk,
            joined_by_id=self.members[0].pk,
            join_reason="Specialist consultation",
        )
        for field, value in changes.items():
            setattr(row, field, value)
        return row
