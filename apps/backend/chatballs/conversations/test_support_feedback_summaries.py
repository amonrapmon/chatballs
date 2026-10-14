"""Approved ST4/ST5 calculations on real PostgreSQL test storage."""

import json

from django.utils import timezone

from chatballs.ai.pseudonymization import Pseudonymizer
from chatballs.conversations.quality.corrections import append_quality_correction
from chatballs.conversations.quality.criteria import configure_quality
from chatballs.conversations.quality.jobs import finish_quality_job, start_quality_job
from chatballs.conversations.quality.models import QualityJob
from chatballs.conversations.quality.validation import validate_output
from chatballs.conversations.support_feedback_test_base import CRITERIA, FeedbackTestBase
from chatballs.conversations.support_filters import ReportFilters
from chatballs.conversations.support_report import calculate_support_report


class FeedbackSummaryTests(FeedbackTestBase):
    def calculate(self, start, end):
        return calculate_support_report(context=self.context, filters=ReportFilters(start, end, "UTC"))

    def test_sent_cohort_and_received_scores_have_separate_half_open_boundaries(self):
        self.reply()
        rating = self.rated(self.complete(), value=4, comment="Thanks")
        request = rating.request
        request.refresh_from_db()
        before = self.calculate(request.sent_at, rating.received_at)["customerRatings"]["scaleSummaries"][0]
        self.assertEqual((before["ratingCount"], before["meanValue"]), (0, None))
        self.assertEqual((before["delivery"]["sentCount"], before["delivery"]["answeredCount"]), (1, 0))
        after = self.calculate(rating.received_at, timezone.now())["customerRatings"]["scaleSummaries"][0]
        self.assertEqual((after["ratingCount"], after["meanValue"], after["commentCount"]), (1, 4, 1))
        self.assertEqual((after["delivery"]["sentCount"], after["delivery"]["responseRate"]), (0, None))
        full = self.report()["customerRatings"]["scaleSummaries"][0]
        self.assertEqual(full["delivery"]["responseRate"], 1)
        self.assertEqual([bucket["rate"] for bucket in full["distribution"]], [0, 0, 0, 1, 0])

    def test_scale_snapshots_remain_separate_in_totals_and_overlapping_employee_rows(self):
        self.reply()
        self.reply(user=self.colleague.user)
        self.rated(self.complete(), value=2)
        self.policy.scale[0]["label"] = "Different meaning"
        self.policy.save()
        self.rated(self.complete(), value=5)
        report = self.report()
        groups = report["customerRatings"]["scaleSummaries"]
        self.assertEqual([row["meanValue"] for row in groups], [2, 5])
        self.assertEqual(len({row["scaleId"] for row in groups}), 2)
        for employee in report["employees"]:
            own = employee["customerRatings"]["scaleSummaries"]
            expected = groups if employee["employee"] in [self.user.pk, self.colleague.user_id] else []
            self.assertEqual(own, expected)

    def test_missing_score_correction_and_unused_version_keep_distinct_meanings(self):
        self.reply()
        event = self.complete()
        job = QualityJob.objects.get(completion_event_id=event.operation_id)
        output = {"conclusions": [{"code": "resolution", "value": None,
                                   "missingReason": "insufficient_messages", "explanation": "Too little evidence",
                                   "recommendations": [], "messageIds": []}]}
        validated = validate_output(json.dumps(output), job, Pseudonymizer())
        start_quality_job(context=self.context, job_id=job.pk)
        finish_quality_job(context=self.context, job_id=job.pk, validated_result=validated)
        first = self.report()["qualityAnalysis"]["versions"][0]
        self.assertEqual(first["analysisCount"], 1)
        self.assertEqual(first["criteria"][0]["missingCount"], 1)
        self.assertIsNone(first["criteria"][0]["effectiveSummary"]["value"])
        append_quality_correction(context=self.context, result_id=job.result.pk, expected_revision=0,
                                  criterion_code="resolution", value=0, reason="Evidence reviewed")
        append_quality_correction(context=self.context, result_id=job.result.pk, expected_revision=1,
                                  criterion_code="resolution", value=2, reason="Additional evidence")
        configure_quality(context=self.context, enabled=True, criteria=CRITERIA)
        unused, corrected = self.report()["qualityAnalysis"]["versions"]
        self.assertEqual((unused["analysisCount"], unused["criteria"][0]["missingCount"]), (0, None))
        self.assertEqual((corrected["correctionRate"], corrected["criteria"][0]["correctedCount"]), (1, 1))
        self.assertEqual(corrected["criteria"][0]["missingCount"], 0)
        self.assertIsNone(corrected["criteria"][0]["originalSummary"]["value"])
        self.assertEqual(corrected["criteria"][0]["effectiveSummary"]["value"], 2)
        self.assertEqual(corrected["validTo"], unused["validFrom"])
        job.result.refresh_from_db()
        self.assertIsNone(job.result.data["conclusions"][0]["value"])

    def test_binary_positive_value_is_explicit_and_names_are_preserved(self):
        configure_quality(context=self.context, enabled=True, criteria=[{
            "code": "resolution", "name": "Resolution", "description": "Issue was resolved",
            "scale": ["Yes", "No"], "reporting": {"positiveValue": "Yes"},
        }])
        self.reply()
        self.analyzed(self.complete(), value="Yes")
        self.analyzed(self.complete(), value="No")
        first = self.report()["qualityAnalysis"]["versions"][0]
        self.assertEqual(first["analysisCount"], 2)
        self.assertEqual(first["criteria"][0]["name"], "Resolution")
        self.assertEqual(first["criteria"][0]["effectiveSummary"], {
            "kind": "positiveRate", "positiveValue": "Yes", "value": 0.5,
        })
        configure_quality(context=self.context, enabled=True, criteria=[{
            "code": "resolution", "description": "Issue was resolved", "scale": ["Yes", "No"],
        }])
        self.analyzed(self.complete(), value="Yes")
        self.assertEqual(self.report()["qualityAnalysis"]["versions"][0]["criteria"][0]["effectiveSummary"],
                         {"kind": "unavailable", "value": None})
