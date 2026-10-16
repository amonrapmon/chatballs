from django.db import DatabaseError, transaction

from chatballs.conversations.ai_turn import AI_TURN_REQUESTED
from chatballs.conversations.email_thread_models import EmailThread, EmailThreadMessage
from chatballs.conversations.email_workflow_test_base import EmailWorkflowTestBase
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import ConnectionIdentity, Contact, Conversation, Message
from chatballs.conversations.transports.base import InboundMessage


class EmailInboundTests(EmailWorkflowTestBase):
    def inbound(self, operation, **changes):
        external_id = changes.get("external_id", "<incoming@mail-data.test>")
        return InboundMessage(**{
            "external_id": "<incoming@mail-data.test>", "user_id": self.contact.email,
            "chat_id": self.contact.email, "text": "Customer reply", "display_name": "Customer",
            "thread_meta": {"last_message_id": external_id,
                            "in_reply_to": operation.letter.mail_message_id, "references": []}, **changes,
        })

    def test_reply_joins_original_web_contact_and_duplicate_message_id_is_skipped(self):
        operation = self.send()
        Contact.objects.create(organization=self.organization, name="Different person", email=self.contact.email)
        identities = ConnectionIdentity.objects.count()
        inbound = self.inbound(operation)
        ingest_inbound(self.mailbox, inbound)
        ingest_inbound(self.mailbox, inbound)
        self.assertEqual(Message.objects.filter(conversation=self.conversation, author_type="CONTACT").count(), 1)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 2)
        self.assertEqual(ConnectionIdentity.objects.count(), identities)
        letter = EmailThreadMessage.objects.get(direction="INBOUND")
        self.assertEqual(letter.message.conversation_id, self.conversation.pk)
        self.assertEqual(letter.in_reply_to, operation.letter.mail_message_id)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.expected_responder, "OPERATOR")
        self.assertEqual(self.conversation.domain_events.filter(actor_kind="CONTACT", transport="EMAIL").count(), 1)

    def test_references_route_and_unlinked_wrong_sender_or_mailbox_use_ordinary_flow(self):
        operation = self.send()
        ingest_inbound(self.mailbox, self.inbound(operation, thread_meta={
            "last_message_id": "<incoming@mail-data.test>", "references": [operation.letter.mail_message_id],
        }))
        self.assertEqual(Message.objects.filter(conversation=self.conversation, author_type="CONTACT").count(), 1)
        cases = [
            (self.mailbox, {"user_id": "different@mail-data.test", "chat_id": "different@mail-data.test"}),
            (self.other_mailbox, {}),
            (self.mailbox, {"thread_meta": {"subject": "Unlinked", "last_message_id": "<unlinked@mail-data.test>"}}),
        ]
        for index, (mailbox, changes) in enumerate(cases):
            ingest_inbound(mailbox, self.inbound(operation, external_id=f"<ordinary-{index}@mail-data.test>", **changes))
        self.assertEqual(Message.objects.filter(conversation=self.conversation, author_type="CONTACT").count(), 1)
        self.assertTrue(Conversation.objects.filter(connection=self.other_mailbox).exists())
        self.assertTrue(Conversation.objects.filter(connection=self.mailbox).exists())
        self.assertGreater(Contact.objects.count(), 1)

    def test_closed_thread_creates_one_linked_web_dialog_with_historical_recipient(self):
        operation = self.send()
        Conversation.objects.filter(pk=self.conversation.pk).update(lifecycle="CLOSED")
        self.contact.email = "changed@mail-data.test"
        self.contact.save()
        inbound = self.inbound(operation, user_id=operation.letter.thread.recipient)
        ingest_inbound(self.mailbox, inbound)
        next_dialog = Conversation.objects.get(previous_conversation=self.conversation)
        self.assertEqual((next_dialog.connection_id, next_dialog.channel_id, next_dialog.contact_id, next_dialog.group_id),
                         (self.web.pk, self.channel.pk, self.contact.pk, self.group.pk))
        self.assertEqual((next_dialog.lifecycle, next_dialog.control_mode), ("OPEN", "PAUSED"))
        self.assertIsNone(next_dialog.assigned_operator_id)
        self.assertEqual(next_dialog.email_threads.get().previous_thread_id, operation.letter.thread_id)
        ingest_inbound(self.mailbox, self.inbound(operation, external_id="<next@mail-data.test>",
            user_id=operation.letter.thread.recipient, thread_meta={"last_message_id": "<next@mail-data.test>",
            "in_reply_to": operation.letter.mail_message_id}))
        self.assertEqual(Conversation.objects.count(), 2)
        self.assertEqual(next_dialog.messages.filter(author_type="CONTACT").count(), 2)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.lifecycle, "CLOSED")
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(list(next_dialog.domain_events.values_list("event_type", "transport")),
                         [("FOLLOW_UP", "EMAIL"), ("QUEUE_ENTERED", "EMAIL"),
                          ("PUBLIC_REPLY", "EMAIL"), ("PUBLIC_REPLY", "EMAIL")])

    def test_database_rejects_forged_followup_route(self):
        operation = self.send()
        previous = operation.letter.thread
        with self.assertRaises(DatabaseError), transaction.atomic():
            EmailThread.objects.bulk_create([EmailThread(
                organization=self.organization, previous_thread=previous, conversation=self.conversation,
                connection=self.other_mailbox, recipient=previous.recipient, subject=previous.subject,
            )])

    def test_mail_reply_queues_ai_source_without_starting_web_ai_turn(self):
        operation = self.send()
        Conversation.objects.filter(pk=self.conversation.pk).update(control_mode="AI", assigned_operator=None)
        ingest_inbound(self.mailbox, self.inbound(operation))
        self.conversation.refresh_from_db()
        self.assertEqual((self.conversation.control_mode, self.conversation.expected_responder), ("PAUSED", "OPERATOR"))
        self.assertIsNotNone(self.conversation.waiting_since)
        self.assertEqual(self.conversation.connection_id, self.web.pk)
        self.assertEqual(self.conversation.domain_events.filter(event_type="QUEUE_ENTERED", transport="EMAIL").count(), 1)
        from chatballs.events.models import OutboxEvent

        self.assertFalse(OutboxEvent.objects.filter(event_type=AI_TURN_REQUESTED).exists())

    def test_old_thread_deletion_keeps_successor_history(self):
        operation = self.send()
        Conversation.objects.filter(pk=self.conversation.pk).update(lifecycle="CLOSED")
        ingest_inbound(self.mailbox, self.inbound(operation))
        successor = Conversation.objects.get(previous_conversation=self.conversation)
        self.conversation.delete()
        successor.refresh_from_db()
        self.assertIsNone(successor.previous_conversation_id)
        self.assertIsNone(successor.email_threads.get().previous_thread_id)
        self.assertEqual(successor.messages.filter(author_type="CONTACT").count(), 1)
