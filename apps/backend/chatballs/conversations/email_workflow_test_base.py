"""Isolated Django test records; no SMTP server, API substitute or seed."""

from chatballs.conversations.email_continuation import send_email_reply
from chatballs.conversations.email_continuation_test_base import EmailContinuationTestBase
from chatballs.conversations.models import Conversation
from chatballs.testing import TenantAPIClient as APIClient


class EmailWorkflowTestBase(EmailContinuationTestBase):
    def setUp(self):
        self.mailbox.config = {
            "email": "support@mail-data.test", "smtp_host": "mail-data.test", "imap_host": "mail-data.test",
        }
        self.mailbox.secret = "unused-in-domain-tests"
        self.mailbox.save()
        Conversation.objects.filter(pk=self.conversation.pk).update(control_mode="HUMAN")
        self.conversation.refresh_from_db()
        self.client = APIClient()
        self.client.force_authenticate(self.member.user)

    def url(self, suffix, conversation=None):
        conversation = conversation or self.conversation
        return f"/api/v1/organizations/{self.organization.public_id}/conversations/{conversation.pk}/{suffix}"

    def send(self, **changes):
        return send_email_reply(**{
            "context": self.context, "conversation_id": self.conversation.pk,
            "recipient": self.contact.email, "connection_id": self.mailbox.pk,
            "text": "Public mail reply", "client_key": "send-request", "subject": "Web enquiry",
            **changes,
        })[0]

    def post_send(self, **changes):
        return self.client.post(self.url("email/operations/"), {
            "recipient": self.contact.email, "connectionId": self.mailbox.pk,
            "text": "Public mail reply", "clientKey": "send-request", "subject": "Web enquiry", **changes,
        }, format="json")
