"""Reply reminders preserve one deadline across incoming mail continuation."""

from chatballs.conversations.email_workflow_test_base import EmailWorkflowTestBase
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.rules.models import HandlingRule, HandlingRuleKind, RuleExecution
from chatballs.conversations.transports.base import InboundMessage


class EmailReminderTests(EmailWorkflowTestBase):
    def test_incoming_mail_starts_one_wait_and_human_mail_reply_cancels_it(self):
        HandlingRule.objects.create(
            organization=self.organization, kind=HandlingRuleKind.REPLY_REMINDER,
            enabled=True, delay_minutes=4, recipients=["ASSIGNEE"],
        )
        operation = self.send()
        response_fact = self.conversation.domain_events.get(
            event_type="PUBLIC_REPLY", actor_kind="HUMAN",
        )

        def receive(number):
            external_id = f"<customer-{number}@mail-data.test>"
            ingest_inbound(self.mailbox, InboundMessage(
                external_id=external_id, user_id=self.contact.email,
                chat_id=self.contact.email, text="Customer follow-up", display_name="Customer",
                thread_meta={"last_message_id": external_id,
                             "in_reply_to": operation.letter.mail_message_id},
            ))

        receive(1)
        pending = RuleExecution.objects.get(conversation=self.conversation, action="REMIND_REPLY")
        opening = self.conversation.messages.filter(author_type="CONTACT").get()
        self.assertEqual(pending.source_event_id, response_fact.pk)
        self.assertEqual(pending.started_at, opening.created_at)
        self.assertEqual(pending.status, "PENDING")
        deadline = pending.scheduled_for

        receive(2)
        receive(2)  # Duplicate inbox/outbox input has no second logical effect.
        pending.refresh_from_db()
        self.assertEqual((pending.status, pending.scheduled_for), ("PENDING", deadline))
        self.assertEqual(RuleExecution.objects.filter(conversation=self.conversation).count(), 1)
        self.assertEqual(self.conversation.messages.filter(author_type="CONTACT").count(), 2)

        self.send(client_key="second-reply")
        pending.refresh_from_db()
        self.assertEqual((pending.status, pending.reason), ("SKIPPED", "replied"))
