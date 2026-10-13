"""Formula checks with immutable in-memory timelines, without fake services."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from django.test import SimpleTestCase

from chatballs.conversations.support_filters import ReportFilters, parse_filters
from chatballs.conversations.support_metrics import Metrics
from chatballs.conversations.support_timeline import conversation_observations

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def fact(second, kind, *, employee=1, actor="HUMAN", operation=None, group=10, sequence=None):
    return SimpleNamespace(occurred_at=BASE + timedelta(seconds=second), event_type=kind,
                           responsible_id=employee, initiated_by_id=employee, actor_kind=actor,
                           operation_id=operation or second, sequence=sequence or second,
                           group_id=group, connection_id=20, transport="WEB")


def incoming(second):
    return SimpleNamespace(created_at=BASE + timedelta(seconds=second), pk=second)


class SupportTimelineTests(SimpleTestCase):
    def report(self, events, messages=(), *, start=0, end=100, employee=None, group=None):
        filters = ReportFilters(BASE + timedelta(seconds=start), BASE + timedelta(seconds=end),
                                "UTC", employee=employee, group=group)
        metrics = Metrics()
        observations = conversation_observations(events, messages, filters.end)
        details = [metrics.add(item, 100, filters) for item in observations]
        return metrics.payload(True)["values"], [item for item in details if item]

    def test_assignment_is_not_acceptance_transfer_splits_handling_and_unique_counts(self):
        events = [fact(1, "QUEUE_ENTERED", employee=None), fact(5, "ASSIGNED"),
                  fact(10, "QUEUE_EXITED", employee=None, operation=11),
                  fact(11, "ACCEPTED", operation=11), fact(30, "TRANSFERRED", employee=2),
                  fact(40, "ACCEPTED", employee=2, group=12), fact(70, "CLOSED", employee=2, group=12)]
        values, _ = self.report(events)
        self.assertEqual((values["accepted"], values["completed"], values["transferred"]), (1, 1, 1))
        self.assertEqual(values["handling"]["seconds"], 49)
        self.assertEqual(values["waiting"]["seconds"], 10)
        first, _ = self.report(events, employee=1)
        second, _ = self.report(events, employee=2)
        self.assertEqual((first["handling"]["seconds"], second["handling"]["seconds"]), (19, 30))
        self.assertEqual((first["transferred"], second["receivedTransfers"]), (1, 1))
        assigned, _ = self.report(events[:2])
        self.assertEqual((assigned["accepted"], assigned["handling"]["seconds"]), (0, 0))

    def test_first_reply_client_series_and_ai_are_independent(self):
        events = [fact(1, "QUEUE_ENTERED", employee=None), fact(10, "ACCEPTED"),
                  fact(20, "PUBLIC_REPLY"), fact(35, "PUBLIC_REPLY", employee=None, actor="AI"),
                  fact(50, "PUBLIC_REPLY"), fact(80, "CLOSED")]
        values, _ = self.report(events, [incoming(2), incoming(30), incoming(32), incoming(60)])
        self.assertEqual(values["firstResponse"]["seconds"], 19)
        self.assertEqual(values["subsequentResponse"]["seconds"], 20)
        self.assertEqual((values["humanReplies"], values["aiReplies"]), (2, 1))
        self.assertEqual(values["aiResponse"]["seconds"], 5)
        self.assertEqual(values["subsequentResponse"]["samples"], 1)

    def test_clipped_half_open_period_current_intervals_and_historical_group(self):
        events = [fact(1, "QUEUE_ENTERED"), fact(10, "ACCEPTED"), fact(20, "PUBLIC_REPLY")]
        values, details = self.report(events, start=15, end=20, group=10)
        self.assertEqual(values["accepted"], 0)
        self.assertEqual(values["humanReplies"], 0)
        self.assertEqual(values["handling"]["seconds"], 5)
        self.assertEqual(values["handling"]["currentIntervals"], 1)
        self.assertTrue(all(item["group"] == 10 for item in details))
        other, _ = self.report(events, group=12)
        self.assertEqual(other["handling"]["seconds"], 0)

    def test_return_to_ai_ends_human_handling_and_first_response(self):
        events = [fact(1, "QUEUE_ENTERED"), fact(10, "ACCEPTED"), fact(30, "QUEUE_EXITED")]
        values, _ = self.report(events)
        self.assertEqual(values["handling"]["seconds"], 20)
        self.assertIsNone(values["firstResponse"]["seconds"])

    def test_period_offsets_cover_dst_without_fixed_days_and_reject_ambiguous_dates(self):
        params = {"from": "2026-03-29T00:00:00+01:00", "to": "2026-03-30T00:00:00+02:00", "timezone": "Europe/Berlin"}
        filters = parse_filters(params)
        self.assertEqual((filters.end - filters.start).total_seconds(), 23 * 3600)
        from rest_framework.exceptions import ValidationError
        for changes in ({"from": "2026-03-29"}, {"timezone": "Mars"}, {"employee": "-1"}, {"channel": "1"}):
            with self.assertRaises(ValidationError):
                parse_filters({**params, **changes})
