"""Partial history retains measured values in HTTP and both export formats."""

import csv
from datetime import timedelta
from io import BytesIO, StringIO

from django.utils import timezone
from openpyxl import load_workbook

from chatballs.conversations.domain_event_models import ConversationEventHistoryStart
from chatballs.conversations.domain_events import record_fact
from chatballs.conversations.models import Conversation
from chatballs.conversations.services import claim_conversation, close_conversation
from chatballs.conversations.support_export import export_csv, export_xlsx
from chatballs.conversations.support_export_rows import report_tables
from chatballs.conversations.support_filters import ReportFilters
from chatballs.conversations.support_report import calculate_support_report
from chatballs.conversations.support_report_test_base import SupportReportTestBase
from chatballs.testing import TenantAPIClient


class PartialSupportReportTests(SupportReportTestBase):
    def setUp(self):
        self.available = self.conversation.created_at
        self.end = timezone.now() + timedelta(hours=1)
        ConversationEventHistoryStart.objects.filter(pk=1).update(
            available_from=self.available, sources_available_from=self.available,
        )
        self.url = f"/api/v1/organizations/{self.organization.public_id}/conversations/support-report/"
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.user)

    def report(self, start, end=None, **dimensions):
        return calculate_support_report(context=self.context, filters=ReportFilters(
            start, end or self.end, "UTC", **dimensions,
        ))

    def observed_cycle(self):
        record_fact(self.conversation, "QUEUE_ENTERED")
        claim_conversation(context=self.context, conversation_id=self.conversation.pk)
        record_fact(self.conversation, "PUBLIC_REPLY", actor_kind="HUMAN", initiated_by_id=self.user.pk)
        close_conversation(context=self.context, conversation_id=self.conversation.pk)

    def test_partial_period_retains_counts_intervals_means_and_employee_filters(self):
        self.observed_cycle()
        filters = ReportFilters(self.available - timedelta(days=2), self.end, "UTC", employee=self.user.pk,
                                group=self.group.pk, connection=self.connection.pk, transport="WEB")
        params = {key: value for key, value in filters.payload().items() if value is not None}
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200, response.data)
        report = response.data
        self.assertFalse(report["coverage"]["complete"])
        self.assertEqual(report["coverage"]["availableFrom"], self.available.isoformat())
        values = report["totals"]["values"]
        self.assertEqual((values["accepted"], values["completed"], values["humanReplies"]), (1, 1, 1))
        self.assertIsNone(values["transferred"])
        self.assertGreater(values["handling"]["seconds"], 0)
        self.assertGreater(values["waiting"]["seconds"], 0)
        self.assertEqual(values["firstResponse"]["meanSeconds"], values["firstResponse"]["seconds"])
        self.assertIsNone(values["subsequentResponse"]["meanSeconds"])
        self.assertEqual(report["employees"][0]["metrics"], report["totals"])
        self.assertTrue(all(not value for value in report["totals"]["completeByMetric"].values()))
        tables = report_tables(report)
        workbook = load_workbook(BytesIO(export_xlsx(report)), data_only=False)
        for sheet, (_, rows) in zip(workbook, tables, strict=True):
            self.assertEqual(list(sheet.values), [tuple("Нет данных" if value is None else None if value == "" else value
                                                       for value in row) for row in rows])
        csv_rows = list(csv.reader(StringIO(export_csv(report).decode("utf-8-sig"))))
        accepted = next(row for row in csv_rows if len(row) > 4 and row[0] == "totals" and row[3] == "accepted")
        self.assertEqual(accepted[5:7], ["1", "1"])
        self.assertEqual(accepted[8], "False")

    def test_unavailable_slice_and_available_slice_do_not_hide_each_other(self):
        self.observed_cycle()
        Conversation.objects.filter(pk=self.conversation.pk).update(created_at=self.available - timedelta(days=3))
        earlier = self.report(self.available - timedelta(days=2), self.available)
        later = self.report(self.available)
        self.assertIsNone(earlier["totals"]["values"]["accepted"])
        self.assertIsNone(earlier["totals"]["values"]["handling"]["seconds"])
        self.assertEqual(later["totals"]["values"]["accepted"], 1)
        self.assertEqual(later["totals"]["values"]["transferred"], 0)
        self.assertTrue(later["totals"]["completeByMetric"]["transferred"])
        self.assertFalse(later["totals"]["completeByMetric"]["handling"])
        self.assertGreater(later["totals"]["values"]["handling"]["seconds"], 0)

    def test_missing_start_is_not_reconstructed_from_closing_event(self):
        Conversation.objects.filter(pk=self.conversation.pk).update(created_at=self.available - timedelta(days=3))
        record_fact(self.conversation, "CLOSED")
        report = self.report(self.available - timedelta(days=1))
        self.assertEqual(report["totals"]["values"]["completed"], 1)
        self.assertIsNone(report["totals"]["values"]["accepted"])
        for key in ("waiting", "handling", "firstResponse", "subsequentResponse"):
            self.assertIsNone(report["totals"]["values"][key]["seconds"])
            self.assertEqual(report["totals"]["values"][key]["samples"], 0)
