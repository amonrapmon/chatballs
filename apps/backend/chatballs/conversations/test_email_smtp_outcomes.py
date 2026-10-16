"""SMTP library boundary tests; no mail server or application API is started."""

import smtplib
from unittest import mock

from chatballs.conversations.email_delivery import deliver_email_reply
from chatballs.conversations.email_workflow_test_base import EmailWorkflowTestBase
from chatballs.conversations.transports import email_smtp


class EmailSmtpOutcomeTests(EmailWorkflowTestBase):
    def deliver(self, *, data_error=None, quit_error=None):
        operation = self.send()
        with mock.patch.object(email_smtp.smtplib, "SMTP_SSL") as constructor:
            client = constructor.return_value
            client.send_message.return_value = {}
            client.send_message.side_effect = data_error
            client.quit.side_effect = quit_error
            deliver_email_reply(operation.attempts.get().outbox_event.payload, self.context)
        return operation.attempts.get(), client

    def test_final_smtp_acceptance_survives_quit_failure_and_replay(self):
        attempt, client = self.deliver(quit_error=smtplib.SMTPServerDisconnected("private SMTP detail"))
        self.assertEqual((attempt.state, attempt.error_code), ("SMTP_ACCEPTED", ""))
        self.assertIsNotNone(attempt.started_at)
        self.assertIsNotNone(attempt.finished_at)
        client.send_message.assert_called_once()
        outgoing = client.send_message.call_args.args[0]
        self.assertEqual(str(outgoing["Message-ID"]), attempt.operation.letter.mail_message_id)
        # Terminal replay must return before even constructing a SMTP client.
        deliver_email_reply(attempt.outbox_event.payload, self.context)
        self.assertEqual(self.conversation.domain_events.count(), 1)

    def test_data_disconnect_is_unknown_and_negative_data_response_is_failed(self):
        for error, expected in (
            (smtplib.SMTPServerDisconnected("private secret"), ("UNKNOWN", "TRANSPORT_ERROR")),
            (smtplib.SMTPDataError(550, b"private secret"), ("FAILED", "SMTP_REJECTED")),
        ):
            # Separate operation keys within one test transaction.
            from chatballs.conversations.email_attempt_models import EmailSendOperation

            key = f"smtp-{EmailSendOperation.objects.count()}"
            operation = self.send(client_key=key)
            with mock.patch.object(email_smtp.smtplib, "SMTP_SSL") as constructor:
                constructor.return_value.send_message.side_effect = error
                deliver_email_reply(operation.attempts.get().outbox_event.payload, self.context)
            attempt = operation.attempts.get()
            self.assertEqual((attempt.state, attempt.error_code), expected)
            self.assertNotIn("private", attempt.error_code)
