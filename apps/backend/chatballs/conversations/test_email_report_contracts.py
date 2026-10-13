from datetime import timedelta

from django.utils import timezone

from chatballs.conversations.domain_events import record_fact
from chatballs.conversations.email_workflow_test_base import EmailWorkflowTestBase
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.support_filters import ReportFilters
from chatballs.conversations.support_report import calculate_support_report
from chatballs.conversations.transports.base import InboundMessage


class EmailReportContractTests(EmailWorkflowTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.member.role = "ADMIN"
        cls.member.save(update_fields=["role"])

    def test_customer_mail_fact_is_not_ai_reply_and_preserves_human_response(self):
        record_fact(self.conversation, "ASSIGNED", actor_kind="SYSTEM")
        operation = self.send()
        inbound = InboundMessage(
            external_id="<report-incoming@mail-data.test>", user_id=self.contact.email,
            chat_id=self.contact.email, text="Customer mail reply", display_name="Customer",
            thread_meta={"last_message_id": "<report-incoming@mail-data.test>",
                         "in_reply_to": operation.letter.mail_message_id},
        )
        ingest_inbound(self.mailbox, inbound)
        ingest_inbound(self.mailbox, inbound)
        self.send(client_key="second-reply", text="Second human reply")
        report = calculate_support_report(context=self.context, filters=ReportFilters(
            self.conversation.created_at, timezone.now() + timedelta(minutes=1), "UTC",
            transport="EMAIL", connection=self.mailbox.pk,
        ))
        counts = report["totals"]["observedCounts"]
        self.assertEqual((counts["humanReplies"], counts["aiReplies"]), (2, 0))
        values = report["totals"]["values"]
        self.assertEqual(values["subsequentResponse"]["samples"], 1)
        self.assertEqual(values["aiResponse"]["samples"], 0)
        self.assertEqual(self.conversation.domain_events.filter(
            event_type="PUBLIC_REPLY", actor_kind="CONTACT", transport="EMAIL",
        ).count(), 1)
