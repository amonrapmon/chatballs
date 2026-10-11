from uuid import uuid4

from django.test import TestCase, TransactionTestCase

from chatballs.channels.models import Channel
from chatballs.conversations.audience import ConversationAudience
from chatballs.conversations.comment_models import ConversationComment
from chatballs.conversations.models import Contact, Conversation
from chatballs.identity.models import HumanUser, Organization, OrganizationMembership
from chatballs.tenancy.context import TenantContext


class CommentTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(name="Comments", slug="comments")
        cls.foreign = Organization.objects.create(name="Foreign", slug="foreign-comments")
        cls.author = HumanUser.objects.create_user(email="author@comments.test")
        cls.membership = OrganizationMembership.objects.create(
            organization=cls.organization, user=cls.author, role="OWNER"
        )
        cls.foreign_author = HumanUser.objects.create_user(email="foreign@comments.test")
        OrganizationMembership.objects.create(
            organization=cls.foreign, user=cls.foreign_author, role="OWNER"
        )
        cls.conversation = cls.make_conversation(cls.organization, "main")
        cls.foreign_conversation = cls.make_conversation(cls.foreign, "foreign")

    @staticmethod
    def make_conversation(organization, code):
        channel = Channel.objects.create(organization=organization, code=code, name=code)
        contact = Contact.objects.create(organization=organization, name="Customer")
        return Conversation.objects.create(organization=organization, channel=channel, contact=contact)

    def setUp(self):
        self.context = TenantContext.for_membership(self.membership)

    def row(self, **changes):
        return ConversationComment(**{
            "organization_id": self.organization.pk,
            "conversation_id": self.conversation.pk,
            "author_id": self.author.pk,
            "audience": ConversationAudience.INTERNAL,
            "text": "Internal discussion",
            "operation_id": uuid4(),
            **changes,
        })

    def comment(self, **changes):
        row = self.row(**changes)
        row.save()
        return row


class CommentTransactionTestBase(TransactionTestCase):
    make_conversation = staticmethod(CommentTestBase.make_conversation)

    def setUp(self):
        CommentTestBase.setUpTestData.__func__(type(self))
        self.context = TenantContext.for_membership(self.membership)
