import smtplib
from email import message_from_bytes, policy

from django.utils import timezone

from chatballs.conversations.email_attempt_models import EmailSendAttempt
from chatballs.conversations.email_continuation import retry_email_reply
from chatballs.conversations.email_delivery import (
    EmailAttemptInProgress,
    begin_attempt,
    finish_attempt,
)
from chatballs.conversations.email_workflow_test_base import EmailWorkflowTestBase
from chatballs.conversations.services import ClaimError
from chatballs.conversations.transports.email import _normalize
from chatballs.conversations.transports.email_smtp import (
    MailOutcome,
    continuation_message,
    deliver_message,
    failure_outcome,
)
from chatballs.events.handlers import dispatch


class EmailDeliveryTests(EmailWorkflowTestBase):
    def test_smtp_message_uses_persisted_route_and_id(self):
        operation = self.send()
        outgoing = continuation_message(operation.letter)
        parsed = message_from_bytes(outgoing.as_bytes(), policy=policy.default)
        self.assertEqual(str(parsed["Message-ID"]), operation.letter.mail_message_id)
        self.assertEqual(str(parsed["To"]), self.contact.email)
        self.assertEqual(str(parsed["From"]), self.mailbox.config["email"])
        self.assertEqual(str(parsed["Subject"]), "Web enquiry")
        followup = self.send(client_key="followup")
        parsed = continuation_message(followup.letter)
        self.assertEqual(str(parsed["In-Reply-To"]), operation.letter.mail_message_id)
        self.assertEqual(str(parsed["References"]), operation.letter.mail_message_id)

    def test_factual_error_classification_and_unavailable_connection(self):
        for error in (smtplib.SMTPDataError(550, b"secret provider error"),
                      smtplib.SMTPRecipientsRefused({self.contact.email: (550, b"secret")})):
            self.assertEqual(failure_outcome(error, sending=True), MailOutcome("FAILED", "SMTP_REJECTED"))
        self.assertEqual(failure_outcome(TimeoutError("secret"), sending=True), MailOutcome("UNKNOWN", "TRANSPORT_ERROR"))
        self.assertEqual(failure_outcome(OSError("secret"), sending=False), MailOutcome("FAILED", "TRANSPORT_ERROR"))
        self.mailbox.is_active = False
        self.assertEqual(deliver_message(self.mailbox, continuation_message(self.send().letter)),
                         MailOutcome("FAILED", "CONNECTION_UNAVAILABLE"))

    def test_attempt_journal_and_allowed_retry_preserve_logical_message_and_mailbox(self):
        operation = self.send()
        first = operation.attempts.get()
        begin_attempt(self.context, first.outbox_event.payload)
        first.refresh_from_db()
        self.assertEqual(first.state, "SENDING")
        finish_attempt(first, MailOutcome("FAILED", "SMTP_REJECTED"))
        second = retry_email_reply(context=self.context, conversation_id=self.conversation.pk, operation_id=operation.pk)
        self.assertEqual((second.number, second.state), (2, "PENDING"))
        self.assertEqual(second.operation.letter.connection_id, self.mailbox.pk)
        self.assertEqual(second.operation.letter.message_id, operation.letter.message_id)
        with self.assertRaises(ClaimError):
            retry_email_reply(context=self.context, conversation_id=self.conversation.pk, operation_id=operation.pk)
        begin_attempt(self.context, second.outbox_event.payload)
        second.refresh_from_db()
        finish_attempt(second, MailOutcome("SMTP_ACCEPTED"))
        dispatch(second.outbox_event)
        with self.assertRaises(ClaimError):
            retry_email_reply(context=self.context, conversation_id=self.conversation.pk, operation_id=operation.pk)
        response = self.client.get(self.url("email/operations/"))
        payload = response.json()["items"][0]
        self.assertEqual([row["state"] for row in payload["attempts"]], ["FAILED", "SMTP_ACCEPTED"])
        self.assertFalse(payload["retryAllowed"])
        self.assertFalse(payload["deliveryConfirmed"])
        self.assertNotIn("secret", response.content.decode())

    def test_unknown_requires_acknowledgement_and_cannot_switch_mailbox(self):
        operation = self.send()
        first = operation.attempts.get()
        begin_attempt(self.context, first.outbox_event.payload)
        first.refresh_from_db()
        finish_attempt(first, MailOutcome("UNKNOWN", "TRANSPORT_ERROR"))
        url = self.url(f"email/operations/{operation.pk}/retry/")
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 409)
        response = self.client.post(url, {"acknowledgeUnknown": True, "connectionId": self.other_mailbox.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(operation.letter.connection_id, self.mailbox.pk)
        self.assertEqual(operation.attempts.count(), 2)

    def test_live_duplicate_skips_and_recovered_worker_records_unknown_without_send(self):
        operation = self.send()
        attempt = operation.attempts.get()
        begin_attempt(self.context, attempt.outbox_event.payload)
        with self.assertRaises(EmailAttemptInProgress):
            dispatch(attempt.outbox_event)
        attempt.refresh_from_db()
        self.assertEqual(attempt.state, "SENDING")
        # Lease recovery uses the same production transition with a supplied
        # server time; no SMTP replacement or sleeping for the lease is needed.
        from datetime import timedelta

        from chatballs.conversations.email_delivery import recover_sending_attempt

        recover_sending_attempt(attempt, now=timezone.now() + timedelta(minutes=6))
        dispatch(attempt.outbox_event)
        attempt.refresh_from_db()
        self.assertEqual((attempt.state, attempt.error_code), ("UNKNOWN", "WORKER_INTERRUPTED"))
        self.assertEqual(EmailSendAttempt.objects.count(), 1)

    def test_retry_with_disabled_original_mailbox_is_unavailable(self):
        operation = self.send()
        finish_attempt(operation.attempts.get(), MailOutcome("FAILED", "CONNECTION_UNAVAILABLE"))
        self.mailbox.is_active = False
        self.mailbox.save()
        response = self.client.get(self.url("email/operations/"))
        self.assertFalse(response.json()["items"][0]["retryAllowed"])
        response = self.client.post(self.url(f"email/operations/{operation.pk}/retry/"), {}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(operation.attempts.count(), 1)

    def test_adapter_preserves_reply_headers(self):
        operation = self.send()
        outgoing = continuation_message(operation.letter)
        outgoing.replace_header("From", self.contact.email)
        outgoing["In-Reply-To"] = "<first@mail-data.test>"
        outgoing["References"] = "<older@mail-data.test> <first@mail-data.test>"
        inbound, _ = _normalize(message_from_bytes(outgoing.as_bytes(), policy=policy.default),
                                own_address=self.mailbox.config["email"], fallback_id="fallback")
        self.assertEqual(inbound.thread_meta["in_reply_to"], "<first@mail-data.test>")
        self.assertEqual(inbound.thread_meta["references"], ["<older@mail-data.test>", "<first@mail-data.test>"])

    def test_retry_rejects_operation_from_another_dialog_and_revoked_access(self):
        from chatballs.conversations.email_attempt_models import EmailSendOperation
        from chatballs.conversations.models import Conversation

        operation = self.send()
        attempt = operation.attempts.get()
        finish_attempt(attempt, MailOutcome("FAILED", "CONNECTION_UNAVAILABLE"))
        other = Conversation.objects.create(
            organization=self.organization, channel=self.channel, connection=self.web,
            contact=self.contact, assigned_operator=self.member.user, control_mode="HUMAN",
        )
        with self.assertRaises(EmailSendOperation.DoesNotExist):
            retry_email_reply(context=self.context, conversation_id=other.pk, operation_id=operation.pk)
        self.member.blocked_at = timezone.now()
        self.member.save()
        with self.assertRaises(Conversation.DoesNotExist):
            retry_email_reply(context=self.context, conversation_id=self.conversation.pk, operation_id=operation.pk)
