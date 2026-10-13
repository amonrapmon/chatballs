from uuid import uuid4

from chatballs.conversations.email_workflow_test_base import EmailWorkflowTestBase
from chatballs.conversations.models import ConnectionIdentity, Contact
from chatballs.conversations.services import delete_conversation
from chatballs.tenancy.context import TenantContext
from chatballs.webchat.message_history import messages_payload
from chatballs.webchat.models import WebSession
from chatballs.webchat.observations import record_signal
from chatballs.webchat.testing import create_web_widget


class EmailVisitorAccessTests(EmailWorkflowTestBase):
    def session(self, external_id, contact=None):
        widget = getattr(self, "widget", None)
        if widget is None:
            self.widget = widget = create_web_widget(self.channel, integration=self.web)
        identity = ConnectionIdentity.objects.create(
            contact=contact or self.contact, connection=self.web, external_user_id=external_id,
        )
        return WebSession.objects.create(
            widget=widget, connection=self.web, identity=identity, token_hash=uuid4().hex * 2,
        )

    def test_staff_state_is_own_visitor_session_and_does_not_expose_credentials(self):
        # Web ingest leaves external_chat_id empty: the dialog is found by contact.
        self.conversation.external_chat_id = ""
        self.conversation.save(update_fields=["external_chat_id"])
        expected = self.session(uuid4().hex)
        stranger = Contact.objects.create(organization=self.organization, name="Another visitor")
        other = self.session(uuid4().hex, contact=stranger)
        record_signal(expected, {"tabId": str(uuid4()), "sequence": 1, "kind": "widget_close"})
        record_signal(other, {"tabId": str(uuid4()), "sequence": 1, "kind": "page_hidden"})
        response = self.client.get(self.url("visitor-state/"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["sessions"]), 1)
        row = response.json()["sessions"][0]["tabs"][0]
        self.assertEqual((row["widget"], row["page"], row["departure"]), ("closed", "unknown", "unknown"))
        self.assertNotIn(expected.token_hash, response.content.decode())
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.lifecycle, "OPEN")

    def test_public_web_history_includes_mail_message_without_attempt_details(self):
        session = self.session(self.conversation.external_chat_id)
        operation = self.send()
        payload = messages_payload(session, 0)
        message = next(row for row in payload["messages"] if row["id"] == operation.letter.message_id)
        self.assertEqual(message["text"], "Public mail reply")
        self.assertNotIn("attempts", message)
        self.assertNotIn("recipient", message)
        response = self.client.get(self.url("messages/"))
        row = next(row for row in response.json()["items"] if row["id"] == operation.letter.message_id)
        self.assertEqual(row["transport"], {"provider": "EMAIL", "connectionId": self.mailbox.pk,
                                           "threadId": operation.letter.thread_id, "direction": "OUTBOUND",
                                           "senderAddress": self.mailbox.config["email"], "recipientAddress": self.contact.email,
                                           "subject": "Web enquiry", "mailboxName": self.mailbox.name})

    def test_public_web_history_resets_after_authorized_deletion(self):
        session = self.session(self.conversation.external_chat_id)
        cursor = self.send().letter.message_id
        self.assertFalse(messages_payload(session, 0)["reset"])
        # Only isolated test membership changes; working accounts are untouched.
        self.member.role = "ADMIN"
        self.member.save()
        delete_conversation(context=TenantContext.for_membership(self.member), conversation=self.conversation)
        after = messages_payload(session, cursor)
        self.assertTrue(after["reset"])
        self.assertEqual(after["messages"], [])
