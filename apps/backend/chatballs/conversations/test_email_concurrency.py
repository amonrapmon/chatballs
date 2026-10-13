from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from chatballs.conversations.email_attempt_models import EmailSendOperation
from chatballs.conversations.email_continuation import send_email_reply
from chatballs.conversations.email_continuation_test_base import EmailContinuationTestBase
from chatballs.conversations.email_thread_models import EmailThreadMessage
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import Conversation, Message
from chatballs.conversations.transports.base import InboundMessage
from chatballs.tenancy.database import tenant_atomic


class EmailConcurrencyTests(TransactionTestCase):
    make_member = staticmethod(EmailContinuationTestBase.make_member)
    make_connection = staticmethod(EmailContinuationTestBase.make_connection)

    def setUp(self):
        EmailContinuationTestBase.setUpTestData.__func__(type(self))
        self.mailbox.config = {"email": "support@mail-data.test", "smtp_host": "mail-data.test", "imap_host": "mail-data.test"}
        self.mailbox.secret = "unused-in-domain-tests"
        self.mailbox.save()
        Conversation.objects.filter(pk=self.conversation.pk).update(control_mode="HUMAN")

    def concurrent(self, action):
        barrier = Barrier(2)

        def run():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET ROLE chatballs_runtime_app")
                barrier.wait(timeout=10)
                with tenant_atomic(self.context):
                    return action()
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [executor.submit(run) for _ in range(2)]
            return [result.result(timeout=20) for result in results]

    def send(self):
        return send_email_reply(
            context=self.context, conversation_id=self.conversation.pk,
            recipient=self.contact.email, connection_id=self.mailbox.pk,
            text="Concurrent reply", subject="Web enquiry", client_key="concurrent",
        )

    def test_concurrent_client_key_creates_one_atomic_operation(self):
        results = self.concurrent(self.send)
        self.assertEqual({operation.pk for operation, _ in results}, {EmailSendOperation.objects.get().pk})
        self.assertEqual(sorted(created for _, created in results), [False, True])
        self.assertEqual(Message.objects.filter(author_type="OPERATOR").count(), 1)
        self.assertEqual(EmailSendOperation.objects.get().attempts.count(), 1)

    def test_concurrent_inbound_message_id_and_closed_thread_create_one_successor(self):
        with tenant_atomic(self.context):
            operation, _ = self.send()
        Conversation.objects.filter(pk=self.conversation.pk).update(lifecycle="CLOSED")
        inbound = InboundMessage(
            external_id="<concurrent-inbound@mail-data.test>", user_id=self.contact.email,
            chat_id=self.contact.email, text="Concurrent incoming", display_name="Visitor",
            thread_meta={"last_message_id": "<concurrent-inbound@mail-data.test>",
                         "in_reply_to": operation.letter.mail_message_id},
        )
        self.concurrent(lambda: ingest_inbound(self.mailbox, inbound))
        self.assertEqual(Conversation.objects.filter(previous_conversation=self.conversation).count(), 1)
        self.assertEqual(EmailThreadMessage.objects.filter(direction="INBOUND").count(), 1)
        self.assertEqual(Message.objects.filter(author_type="CONTACT").count(), 1)
