from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction

from chatballs.conversations.email_attempt_models import EmailSendOperation
from chatballs.conversations.email_continuation_test_base import (
    EmailContinuationTestBase,
)
from chatballs.conversations.email_thread_models import EmailThread, EmailThreadMessage
from chatballs.conversations.models import (
    ConnectionIdentity,
    Contact,
    ContactMerge,
    Conversation,
)


class EmailContinuationModelTests(EmailContinuationTestBase):
    def test_mail_registry_preserves_web_source_and_does_not_merge_equal_emails(self):
        other_contact = Contact.objects.create(organization=self.organization, email=self.contact.email)
        original = Conversation.objects.filter(pk=self.conversation.pk).values().get()
        thread = self.thread(organization_id=None, recipient=" VISITOR@MAIL-DATA.TEST ")
        thread.save()
        letter = self.letter(thread, in_reply_to="<question@example.test>", references=["<question@example.test>"])
        letter.save()
        thread.refresh_from_db()
        letter.refresh_from_db()
        self.assertEqual(thread.organization_id, self.organization.pk)
        self.assertEqual(thread.recipient, self.contact.email)
        self.assertEqual(thread.subject, "Web enquiry")
        self.assertEqual(thread.connection_id, self.mailbox.pk)
        self.assertEqual(letter.message.email_transport, letter)
        self.assertEqual(letter.in_reply_to, "<question@example.test>")
        self.assertEqual(letter.references, ["<question@example.test>"])
        self.assertEqual(letter.mail_message_id, f"<reply-{letter.message_id}@mail-data.test>")
        # Message creation moves activity timestamps; routing and assignment remain unchanged.
        current = Conversation.objects.filter(pk=self.conversation.pk).values().get()
        for field in ("channel_id", "connection_id", "contact_id", "group_id", "assigned_operator_id",
                      "external_chat_id", "transport_meta", "lifecycle", "control_mode"):
            self.assertEqual(current[field], original[field])
        self.assertEqual(self.conversation.channel.ai_agent.pk, self.agent.pk)
        self.assertFalse(ContactMerge.objects.exists())
        other_contact.refresh_from_db()
        self.contact.refresh_from_db()
        self.assertIsNone(other_contact.merged_into_id)
        self.assertIsNone(self.contact.merged_into_id)
        self.assertFalse(ConnectionIdentity.objects.exists())

    def test_saved_email_identity_is_allowed_without_identity_merge(self):
        identity = ConnectionIdentity.objects.create(
            contact=self.contact, connection=self.mailbox, external_user_id="additional@mail-data.test",
        )
        thread = self.thread(recipient=identity.external_user_id)
        thread.save()
        self.assertEqual(thread.conversation.contact_id, identity.contact_id)
        self.assertEqual(ConnectionIdentity.objects.count(), 1)

    def test_thread_rejects_arbitrary_email_inactive_or_non_email_mailbox_and_non_web_source(self):
        self.other_mailbox.is_active = False
        self.other_mailbox.save(update_fields=["is_active"])
        email_conversation = Conversation.objects.create(
            organization=self.organization, channel=self.mail_channel, connection=self.mailbox, contact=self.contact,
        )
        for changes in (
            {"recipient": "stranger@example.test"}, {"recipient": "invalid"},
            {"connection": self.web}, {"connection": self.other_mailbox},
            {"conversation": email_conversation}, {"connection": self.foreign_mailbox},
            {"organization": self.foreign},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.thread(**changes).save()

    def test_letter_checks_conversation_mailbox_and_tenant(self):
        thread = self.thread()
        thread.save()
        other = Conversation.objects.create(organization=self.organization, channel=self.channel, contact=self.contact)
        letter = self.letter(thread)
        for field, value in (("connection", self.other_mailbox), ("organization", self.foreign)):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.letter(thread, **{field: value}).save()
        letter.message.conversation = other
        letter.message.save()
        with self.assertRaises(ValidationError):
            letter.save()

    def test_operation_requires_outbound_letter_and_local_initiator(self):
        thread = self.thread()
        thread.save()
        inbound = self.letter(thread, direction="INBOUND")
        inbound.save()
        with self.assertRaises(ValidationError):
            EmailSendOperation.objects.create(letter=inbound, initiated_by=self.member, client_key="inbound")
        outbound = self.letter(thread)
        outbound.save()
        with self.assertRaises(ValidationError):
            EmailSendOperation.objects.create(letter=outbound, initiated_by=self.foreign_member, client_key="foreign")

    def test_message_id_is_unique_per_mailbox_and_client_key_per_organization(self):
        operation = self.operation()
        with self.assertRaises(DatabaseError), transaction.atomic():
            self.letter(operation.letter.thread, mail_message_id=operation.letter.mail_message_id).save()
        other_thread = self.thread(connection=self.other_mailbox)
        other_thread.save()
        other_letter = self.letter(other_thread, mail_message_id=operation.letter.mail_message_id)
        other_letter.save()
        with self.assertRaises(DatabaseError), transaction.atomic():
            EmailSendOperation.objects.create(letter=other_letter, initiated_by=self.member, client_key=operation.client_key)
        self.assertEqual(EmailSendOperation.objects.count(), 1)
        self.assertEqual(EmailThreadMessage.objects.count(), 2)
        self.assertEqual(EmailThread.objects.count(), 2)

    def test_existing_snapshot_survives_contact_email_edit_and_mailbox_disable(self):
        operation = self.operation()
        thread = operation.letter.thread
        self.contact.email = "changed@example.test"
        self.contact.save(update_fields=["email"])
        self.mailbox.is_active = False
        self.mailbox.save(update_fields=["is_active"])
        thread.subject = "Follow-up"
        thread.save(update_fields=["subject"])
        thread.refresh_from_db()
        self.assertEqual(thread.recipient, "visitor@mail-data.test")
        self.assertEqual(thread.connection_id, self.mailbox.pk)
