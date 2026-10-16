"""Agent-independent continuation: staff API, outbox gate and real DB routing."""

from unittest import mock

from chatballs.conversations import poller
from chatballs.conversations.email_delivery import begin_attempt
from chatballs.conversations.email_options import mailbox_available
from chatballs.conversations.email_workflow_test_base import EmailWorkflowTestBase
from chatballs.conversations.models import Contact, Conversation, Message
from chatballs.conversations.transports.base import InboundMessage
from chatballs.integrations.models import Integration
from chatballs.tenancy.database import tenant_atomic


class EmailAgentIndependenceTests(EmailWorkflowTestBase):
    def setUp(self):
        super().setUp()
        for mailbox in (self.mailbox, self.other_mailbox, self.foreign_mailbox):
            mailbox.channel = None
            mailbox.config = {**self.mailbox.config, "email": f"mailbox-{mailbox.pk}@mail-data.test"}
            mailbox.secret = "unused-in-domain-tests"
            mailbox.save()

    def inbound(self, *, reference="", sender=None, external_id="<incoming@mail-data.test>"):
        return InboundMessage(
            external_id=external_id, user_id=sender or self.contact.email,
            chat_id=sender or self.contact.email, text="Customer reply", display_name="Customer",
            thread_meta={"last_message_id": external_id, "in_reply_to": reference, "references": []},
        )

    def poll(self, messages, mailbox=None):
        mailbox = mailbox or self.mailbox

        def transport(connection):
            return (messages, "7:42") if connection.pk == mailbox.pk else ([], connection.poll_marker)

        with tenant_atomic(self.context), mock.patch.object(poller.transports, "poll", side_effect=transport):
            return poller.poll_all_messengers(self.context)

    def test_options_list_both_unbound_mailboxes_without_foreign_rows_or_secrets(self):
        response = self.client.get(self.url("email/options/"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual({row["id"] for row in response.json()["mailboxes"]},
                         {self.mailbox.pk, self.other_mailbox.pk})
        self.assertNotIn(self.foreign_mailbox.pk, [row["id"] for row in response.json()["mailboxes"]])
        self.assertNotIn(self.mailbox.secret, response.content.decode())
        self.assertEqual(self.post_send(connectionId=self.foreign_mailbox.pk).status_code, 409)

    def test_selected_unbound_mailbox_reaches_outbox_without_changing_web_source(self):
        source = (self.conversation.connection_id, self.conversation.channel_id,
                  self.conversation.contact_id, self.conversation.assigned_operator_id)
        response = self.post_send(connectionId=self.other_mailbox.pk)
        self.assertEqual(response.status_code, 201, response.content)
        operation = self.conversation.messages.get(author_type="OPERATOR").email_transport.send_operation
        attempt = operation.attempts.get()
        work = begin_attempt(self.context, attempt.outbox_event.payload)
        self.assertIsNotNone(work)
        self.assertEqual(work[1].connection_id, self.other_mailbox.pk)
        self.conversation.refresh_from_db()
        self.assertEqual(source, (self.conversation.connection_id, self.conversation.channel_id,
                                 self.conversation.contact_id, self.conversation.assigned_operator_id))

    def test_mail_agent_channel_activity_does_not_block_continuation(self):
        self.mailbox.channel = self.mail_channel
        self.mailbox.save()
        self.mail_channel.is_active = False
        self.mail_channel.save()
        self.assertTrue(mailbox_available(self.mailbox))
        operation = self.send()
        self.assertEqual(self.poll([self.inbound(reference=operation.letter.mail_message_id)]), 1)
        self.assertEqual(self.conversation.messages.filter(author_type="CONTACT").count(), 1)

    def test_unbound_mailbox_receives_linked_reply_in_original_web_dialog(self):
        operation = self.send(connection_id=self.other_mailbox.pk)
        inbound = self.inbound(reference=operation.letter.mail_message_id)
        self.assertEqual(self.poll([inbound], self.other_mailbox), 1)
        message = Message.objects.get(author_type="CONTACT")
        self.assertEqual(message.conversation_id, self.conversation.pk)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(self.poll([inbound], self.other_mailbox), 1)
        self.assertEqual(Message.objects.filter(author_type="CONTACT").count(), 1)

    def test_unbound_poll_starts_without_thread_and_does_not_create_unlinked_dialogs(self):
        self.assertEqual(self.poll([self.inbound()]), 0)
        self.mailbox.refresh_from_db()
        self.assertEqual(self.mailbox.poll_marker, "7:42")
        operation = self.send()
        self.assertEqual(self.poll([self.inbound(reference=operation.letter.mail_message_id,
                                                 sender="stranger@mail-data.test")]), 0)
        self.assertEqual(self.poll([self.inbound(reference=operation.letter.mail_message_id)],
                                  self.other_mailbox), 0)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 1)
        self.assertFalse(Message.objects.filter(author_type="CONTACT").exists())

    def test_unbound_reply_to_closed_dialog_keeps_original_web_route(self):
        operation = self.send()
        Conversation.objects.filter(pk=self.conversation.pk).update(lifecycle="CLOSED")
        self.assertEqual(self.poll([self.inbound(reference=operation.letter.mail_message_id)]), 1)
        successor = Conversation.objects.get(previous_conversation=self.conversation)
        self.assertEqual((successor.connection_id, successor.channel_id, successor.contact_id, successor.group_id),
                         (self.web.pk, self.channel.pk, self.contact.pk, self.group.pk))
        self.assertEqual(successor.email_threads.get().connection_id, self.mailbox.pk)
        self.assertEqual(successor.messages.filter(author_type="CONTACT").count(), 1)

    def test_bound_mailbox_keeps_ordinary_inbound_flow(self):
        self.mailbox.channel = self.mail_channel
        self.mailbox.save()
        self.assertEqual(self.poll([self.inbound()]), 1)
        self.assertTrue(Conversation.objects.filter(connection=self.mailbox).exists())

    def test_agent_independence_keeps_mailbox_availability_guards(self):
        original_config = dict(self.mailbox.config)
        original_secret = self.mailbox.secret
        cases = [
            {"status": "ERROR"}, {"is_active": False}, {"secret": ""},
            *({"config": {key: value for key, value in original_config.items() if key != missing}}
              for missing in ("email", "imap_host", "smtp_host")),
            {"config": {**original_config, "demoSeed": True}},
        ]
        for changes in cases:
            with self.subTest(changes=changes.keys()):
                self.mailbox.status = "UNCHECKED"
                self.mailbox.is_active = True
                self.mailbox.secret = original_secret
                self.mailbox.config = original_config
                for key, value in changes.items():
                    setattr(self.mailbox, key, value)
                self.mailbox.save()
                self.assertFalse(mailbox_available(self.mailbox))
                self.assertEqual(self.post_send().status_code, 409)

    def test_polling_keeps_organization_activity_demo_and_nonmail_channel_guards(self):
        unbound_bot = Integration.objects.create(
            organization=self.organization, kind="MESSENGER", provider="TELEGRAM",
            name="Unbound bot", secret="unused-in-domain-tests",
        )
        self.mailbox.config = {**self.mailbox.config, "demoSeed": True}
        self.mailbox.save()
        with tenant_atomic(self.context), mock.patch.object(poller.transports, "poll", return_value=([], "")) as polled:
            poller.poll_all_messengers(self.context)
        self.assertEqual({call.args[0].pk for call in polled.call_args_list}, {self.other_mailbox.pk})
        self.assertNotIn(unbound_bot.pk, {call.args[0].pk for call in polled.call_args_list})
        self.other_mailbox.is_active = False
        self.other_mailbox.save()
        with tenant_atomic(self.context), mock.patch.object(poller.transports, "poll") as polled:
            poller.poll_all_messengers(self.context)
        polled.assert_not_called()
