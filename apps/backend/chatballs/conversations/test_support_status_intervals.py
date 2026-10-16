from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from django.test import SimpleTestCase

from chatballs.conversations.support_status_intervals import status_durations


class StatusIntersectionTests(SimpleTestCase):
    def test_clipping_initial_gap_and_current_interval_without_presence(self):
        start = datetime(2026, 1, 1, tzinfo=UTC)
        transitions = [SimpleNamespace(status="READY", version=1, changed_at=start + timedelta(seconds=10)),
                       SimpleNamespace(status="BREAK", version=2, changed_at=start + timedelta(seconds=30))]
        report = status_durations(transitions, start=start + timedelta(seconds=20),
                                  end=start + timedelta(seconds=60), effective_end=start + timedelta(seconds=50))
        self.assertTrue(report["complete"])
        self.assertEqual(report["values"]["READY"]["seconds"], 10)
        self.assertEqual(report["values"]["BREAK"]["seconds"], 20)
        self.assertEqual(report["values"]["BREAK"]["currentIntervals"], 1)
        partial = status_durations(transitions, start=start, end=start + timedelta(seconds=60),
                                   effective_end=start + timedelta(seconds=50))
        self.assertFalse(partial["complete"])
        self.assertIsNone(partial["values"]["READY"]["seconds"])
        self.assertEqual(partial["values"]["READY"]["observedSeconds"], 20)
        missing = status_durations([], start=start, end=start + timedelta(seconds=60), effective_end=start)
        self.assertIsNone(missing["values"]["UNAVAILABLE"]["seconds"])

    def test_block_permanently_closes_selection_until_next_transition(self):
        start = datetime(2026, 1, 1, tzinfo=UTC)
        transitions = [SimpleNamespace(status="READY", version=1, changed_at=start,
                                      stopped_at=start + timedelta(seconds=20)),
                       SimpleNamespace(status="BUSY", version=2, changed_at=start + timedelta(seconds=50))]
        report = status_durations(transitions, start=start + timedelta(seconds=10),
                                  end=start + timedelta(seconds=80), effective_end=start + timedelta(seconds=70))
        self.assertEqual(report["values"]["READY"]["seconds"], 10)
        self.assertEqual(report["values"]["READY"]["currentIntervals"], 0)
        self.assertEqual(report["values"]["BUSY"]["seconds"], 20)
        self.assertEqual(report["values"]["BUSY"]["currentIntervals"], 1)
        gap = status_durations(transitions[:1], start=start + timedelta(seconds=30),
                               end=start + timedelta(seconds=40), effective_end=start + timedelta(seconds=40))
        self.assertEqual(gap["values"]["READY"]["seconds"], 0)
        unknown = status_durations(transitions[:1], start=start, end=start + timedelta(seconds=40),
                                   effective_end=start + timedelta(seconds=40), tracking_from=start + timedelta(seconds=1))
        self.assertIsNone(unknown["values"]["READY"]["seconds"])
