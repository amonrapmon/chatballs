from django.core.files.uploadedfile import SimpleUploadedFile

from chatballs.conversations.email_attempt_models import EmailSendAttempt, EmailSendOperation
from chatballs.conversations.email_delivery import begin_attempt, finish_attempt
from chatballs.conversations.email_payloads import operation_payload
from chatballs.conversations.email_thread_models import EmailThreadMessage
from chatballs.conversations.email_workflow_test_base import EmailWorkflowTestBase
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import Message
from chatballs.conversations.serializers import message_payload
from chatballs.conversations.transports.base import InboundMessage
from chatballs.conversations.transports.email_smtp import MailOutcome, continuation_message
from chatballs.tenancy.database import tenant_atomic


class EmailUiContractTests(EmailWorkflowTestBase):
    def multipart(self, content=b"receipt", name="receipt.txt", **changes):
        return self.client.post(self.url("email/operations/"), {
            "recipient": self.contact.email, "connectionId": self.mailbox.pk,
            "text": "Attached reply", "clientKey": "file-request", "subject": "Receipt",
            "file": SimpleUploadedFile(name, content, content_type="text/plain"), **changes,
        }, format="multipart")

    def test_address_saved_in_contact_card_becomes_selectable(self):
        self.contact.email = ""
        self.contact.save(update_fields=["email"])
        self.assertEqual(self.client.get(self.url("email/options/")).json()["addresses"], [])
        rejected = self.client.post(self.url("contact/"), {"email": "not-an-address"}, format="json")
        self.assertEqual(rejected.status_code, 400, rejected.content)
        saved = self.client.post(self.url("contact/"), {"email": " Card@Mail-Data.test "}, format="json")
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertEqual(saved.json()["conversation"]["contact"]["email"], "card@mail-data.test")
        self.assertEqual(self.client.get(self.url("email/options/")).json()["addresses"], ["card@mail-data.test"])

    def test_contact_page_email_validation_normalization_and_clear(self):
        from chatballs.identity.models import EmployeeRole

        self.member.role = EmployeeRole.ADMIN
        self.member.save(update_fields=["role"])
        url = f"/api/v1/organizations/{self.organization.public_id}/conversations/clients/{self.contact.pk}/"
        self.assertEqual(self.client.patch(url, {"email": "no-at-sign"}, format="json").status_code, 400)
        saved = self.client.patch(url, {"email": "Ivan@Example.org"}, format="json")
        self.assertEqual(saved.status_code, 200, saved.content)
        self.assertEqual(saved.json()["client"]["email"], "ivan@example.org")
        self.assertEqual(self.client.patch(url, {"email": ""}, format="json").status_code, 200)
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.email, "")

    def test_attachment_is_idempotent_and_retry_uses_saved_mime_and_message_id(self):
        first = self.multipart()
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(self.multipart().status_code, 200)
        self.assertEqual(self.multipart(content=b"different").status_code, 409)
        operation = EmailSendOperation.objects.get(pk=first.json()["operation"]["id"])
        with tenant_atomic(self.context):
            outgoing = continuation_message(operation.letter)
        attachment = list(outgoing.iter_attachments())[0]
        self.assertEqual(attachment.get_payload(decode=True), b"receipt")
        self.assertEqual(attachment.get_filename(), "receipt.txt")
        self.assertEqual(outgoing["Message-ID"], operation.letter.mail_message_id)
        attempt = operation.attempts.get()
        finish_attempt(attempt, MailOutcome("FAILED", "SMTP_REJECTED"))
        response = self.client.post(self.url(f"email/operations/{operation.pk}/retry/"), {}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(Message.objects.filter(pk=operation.letter.message_id).count(), 1)
        with tenant_atomic(self.context):
            retried = continuation_message(operation.letter)
        self.assertEqual(list(retried.iter_attachments())[0].get_payload(decode=True), b"receipt")

    def test_file_policy_and_foreign_mailbox_do_not_create_mail(self):
        for changes in ({"name": "run.exe"}, {"content": b""}, {"connectionId": self.foreign_mailbox.pk}):
            self.assertIn(self.multipart(**changes).status_code, (400, 409))
        self.assertFalse(EmailThreadMessage.objects.exists())
        self.assertFalse(Message.objects.filter(author_type="OPERATOR").exists())

    def test_envelope_is_historical_and_changed_sender_disables_retry_and_dispatch(self):
        operation = self.send()
        sender = self.mailbox.config["email"]
        self.mailbox.config["email"] = "replacement@mail-data.test"
        self.mailbox.name = "Renamed mailbox"
        self.mailbox.save()
        letter = EmailThreadMessage.objects.select_related("thread", "connection", "message").get(pk=operation.letter.pk)
        self.assertEqual(message_payload(letter.message)["transport"]["senderAddress"], sender)
        self.assertEqual(letter.subject, "Web enquiry")
        outgoing = continuation_message(letter)
        self.assertEqual(outgoing["From"], sender)
        operation.letter = letter
        payload = operation_payload(operation, context=self.context)
        self.assertEqual((payload["senderAddress"], payload["mailboxName"]), (sender, "Mail"))
        self.assertIsNone(begin_attempt(self.context, operation.attempts.get().outbox_event.payload))
        attempt = EmailSendAttempt.objects.get(operation=operation)
        self.assertEqual(attempt.error_code, "CONNECTION_UNAVAILABLE")
        self.assertFalse(operation_payload(operation, context=self.context)["retryAllowed"])

    def test_incoming_envelope_and_operation_filter_do_not_require_current_mailbox_options(self):
        operation = self.send()
        inbound = InboundMessage(external_id="<reply-ui@mail-data.test>", user_id=self.contact.email,
                                chat_id=self.contact.email, text="Related response", display_name="Customer", thread_meta={
                                    "last_message_id": "<reply-ui@mail-data.test>",
                                    "in_reply_to": operation.letter.mail_message_id, "subject": "Re: Customer subject",
                                })
        ingest_inbound(self.mailbox, inbound)
        message = Message.objects.get(author_type="CONTACT")
        envelope = message_payload(message)["transport"]
        self.assertEqual((envelope["senderAddress"], envelope["subject"]), (self.contact.email, "Re: Customer subject"))
        self.assertEqual(envelope["recipientAddress"], self.mailbox.config["email"])
        found = self.client.get(self.url(f"email/operations/?messageIds={operation.letter.message_id}&limit=200"))
        self.assertEqual([row["id"] for row in found.json()["items"]], [operation.pk])
        self.assertEqual(self.client.get(self.url("email/operations/?messageIds=999999")).json()["items"], [])
        self.assertEqual(self.client.get(self.url("email/operations/?messageIds=invalid")).status_code, 400)
        self.assertNotIn(self.mailbox.secret, found.content.decode())
