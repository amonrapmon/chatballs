"""Domain records in Django's isolated test database, with real PostgreSQL guards."""

from django.test import TestCase

from chatballs.ai.models import AIAgent
from chatballs.channels.models import Channel
from chatballs.conversations.email_attempt_models import (
    EmailSendAttempt,
    EmailSendOperation,
)
from chatballs.conversations.email_thread_models import EmailThread, EmailThreadMessage
from chatballs.conversations.models import Contact, Conversation, Message
from chatballs.events.models import OutboxEvent
from chatballs.identity.models import (
    EmployeeGroup,
    HumanUser,
    Organization,
    OrganizationMembership,
)
from chatballs.integrations.models import Integration
from chatballs.tenancy.context import TenantContext


class EmailContinuationTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.organization = Organization.objects.create(name="Mail", slug="mail-data")
        cls.foreign = Organization.objects.create(name="Foreign mail", slug="foreign-mail-data")
        cls.member = cls.make_member(cls.organization, "operator@mail-data.test")
        cls.foreign_member = cls.make_member(cls.foreign, "operator@foreign-mail-data.test")
        cls.group = EmployeeGroup.objects.create(organization=cls.organization, name="Web group")
        cls.channel = Channel.objects.create(organization=cls.organization, code="web", name="Web", group=cls.group)
        cls.mail_channel = Channel.objects.create(organization=cls.organization, code="mail", name="Mail")
        cls.agent = AIAgent.objects.create(organization=cls.organization, channel=cls.channel)
        cls.web = cls.make_connection(cls.organization, "WEB", "Web", cls.channel)
        cls.mailbox = cls.make_connection(cls.organization, "EMAIL", "Mail", cls.mail_channel)
        cls.other_mailbox = cls.make_connection(cls.organization, "EMAIL", "Other mail", cls.mail_channel)
        cls.foreign_mailbox = cls.make_connection(cls.foreign, "EMAIL", "Foreign mail")
        cls.contact = Contact.objects.create(organization=cls.organization, email="visitor@mail-data.test")
        cls.conversation = Conversation.objects.create(
            organization=cls.organization, channel=cls.channel, connection=cls.web,
            contact=cls.contact, group=cls.group, assigned_operator=cls.member.user,
            external_chat_id="web-session", transport_meta={"source": "website"},
        )
        cls.context = TenantContext.for_membership(cls.member)

    @staticmethod
    def make_member(organization, email):
        user = HumanUser.objects.create(email=email)
        return OrganizationMembership.objects.create(organization=organization, user=user, role="EMPLOYEE")

    @staticmethod
    def make_connection(organization, provider, name, channel=None):
        return Integration.objects.create(
            organization=organization, kind="MESSENGER", provider=provider,
            name=name, channel=channel, is_active=True,
        )

    def thread(self, **changes):
        return EmailThread(**{
            "organization": self.organization, "conversation": self.conversation,
            "connection": self.mailbox, "recipient": self.contact.email, "subject": "Web enquiry",
            **changes,
        })

    def letter(self, thread, **changes):
        message = Message.objects.create(conversation=thread.conversation, author_type="OPERATOR", text="Reply")
        return EmailThreadMessage(**{
            "organization": thread.organization, "thread": thread, "connection": thread.connection,
            "message": message, "direction": "OUTBOUND", "mail_message_id": f"<reply-{message.pk}@mail-data.test>",
            **changes,
        })

    def operation(self):
        thread = self.thread()
        thread.save()
        letter = self.letter(thread)
        letter.save()
        return EmailSendOperation.objects.create(letter=letter, initiated_by=self.member, client_key=f"request-{letter.pk}")

    def attempt(self, operation, number=1, **changes):
        event = OutboxEvent.objects.create(
            ownership="TENANT", organization=operation.organization, membership=self.member,
            event_type="conversations.email_send_requested", aggregate_type="email_operation",
            aggregate_id=str(operation.pk), payload={"operation_id": operation.pk, "attempt": number},
        )
        return EmailSendAttempt(**{
            "operation": operation, "number": number, "initiated_by": self.member, "outbox_event": event,
            **changes,
        })
