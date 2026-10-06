from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.models import Contact, Conversation
from chatballs.conversations.transfer_models import TransferReason
from chatballs.identity.models import EmployeeRole, HumanUser, Organization, OrganizationMembership
from chatballs.tenancy.context import TenantContext
from chatballs.testing import TenantAPIClient


class TransferTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(name="Transfers", slug="transfers")
        cls.foreign = Organization.objects.create(name="Foreign", slug="foreign-transfers")
        cls.members = {}
        for role in EmployeeRole.values:
            user = HumanUser.objects.create_user(email=f"{role}@transfers.test")
            cls.members[role] = OrganizationMembership.objects.create(
                organization=cls.organization, user=user, role=role
            )
        cls.foreign_user = HumanUser.objects.create_user(email="foreign@transfers.test")
        OrganizationMembership.objects.create(
            organization=cls.foreign, user=cls.foreign_user, role=EmployeeRole.OWNER
        )
        channel = Channel.objects.create(organization=cls.organization, name="Transfer", code="transfer")
        contact = Contact.objects.create(organization=cls.organization, name="Customer")
        cls.conversation = Conversation.objects.create(
            organization=cls.organization, channel=channel, contact=contact,
            assigned_operator=cls.members[EmployeeRole.ADMIN].user,
        )
        foreign_channel = Channel.objects.create(organization=cls.foreign, name="Foreign", code="foreign")
        foreign_contact = Contact.objects.create(organization=cls.foreign, name="Foreign customer")
        cls.foreign_conversation = Conversation.objects.create(
            organization=cls.foreign, channel=foreign_channel, contact=foreign_contact
        )
        cls.reason = TransferReason.objects.create(
            organization=cls.organization, code="specialist", name="Specialist needed"
        )
        cls.foreign_reason = TransferReason.objects.create(
            organization=cls.foreign, code="specialist", name="Foreign reason"
        )

    def setUp(self):
        self.context = TenantContext.for_membership(self.members[EmployeeRole.OWNER])
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.context.actor_user)
        self.url = f"/api/v1/organizations/{self.organization.public_id}/conversations/transfer-reasons/"
