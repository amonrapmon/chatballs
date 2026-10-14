"""Attribution, immutable scales, revision policy and the half-open period."""

from datetime import timedelta
from uuid import uuid4

from django.utils import timezone

from chatballs.conversations.models import ConversationComment, ConversationParticipant, Message
from chatballs.conversations.quality.corrections import append_quality_correction
from chatballs.conversations.quality.criteria import configure_quality
from chatballs.conversations.quality.jobs import (
    finish_quality_job,
    request_quality_job,
    start_quality_job,
)
from chatballs.conversations.support_feedback_test_base import CRITERIA, FeedbackTestBase
from chatballs.conversations.support_filters import ReportFilters
from chatballs.conversations.support_report import calculate_support_report


class FeedbackCalculationTests(FeedbackTestBase):
    def test_actual_responders_overlap_but_totals_count_once_and_assignment_does_not_count(self):
        self.reply()
        self.reply(user=self.colleague.user)
        Message.objects.create(conversation=self.conversation, author_type="AI", text="AI reply")
        self.reply(user=self.idle.user, system_event="operator_assigned")
        ConversationParticipant.objects.create(organization=self.organization, conversation=self.conversation,
                                               membership=self.idle, joined_by=self.member, join_reason="Help")
        ConversationComment.objects.create(organization=self.organization, conversation=self.conversation,
                                           author=self.idle.user, audience="INTERNAL", text="Note", operation_id=uuid4())
        self.conversation.assigned_operator = self.idle.user
        self.conversation.save(update_fields=["assigned_operator"])
        event = self.complete()
        self.rated(event)
        self.analyzed(event)
        report = self.report()
        for source in ("customerRatings", "qualityAnalysis"):
            self.assertEqual(report[source]["count"], 1)
            self.assertEqual(report[source]["details"][0]["responderIds"], sorted([self.user.pk, self.colleague.user_id]))
            counts = {row["employee"]: row[source]["count"] for row in report["employees"]}
            self.assertEqual(counts, {self.user.pk: 1, self.colleague.user_id: 1, self.idle.user_id: 0})
            self.assertEqual(self.report(employee=self.colleague.user_id)[source]["count"], 1)
            self.assertEqual(self.report(employee=self.idle.user_id)[source]["count"], 0)

    def test_scale_snapshots_and_criteria_versions_remain_separate_with_corrections(self):
        self.reply()
        first = self.complete()
        self.rated(first)
        job = self.analyzed(first)
        append_quality_correction(context=self.context, result_id=job.result.pk, expected_revision=0,
                                  criterion_code="resolution", value=2, reason="Reviewed")
        self.policy.scale[0]["label"] = "=Changed label"
        self.policy.save()
        # Even identical scales remain in separate criteria versions.
        configure_quality(context=self.context, enabled=True, criteria=CRITERIA)
        second = self.complete()
        self.rated(second, value=4)
        self.analyzed(second, value=0)
        report = self.report()
        self.assertEqual(report["customerRatings"]["count"], 2)
        self.assertEqual(len(report["customerRatings"]["groups"]), 2)
        groups = sorted(report["qualityAnalysis"]["groups"], key=lambda row: row["criteriaVersion"])
        self.assertEqual([row["criteriaVersion"] for row in groups], [1, 2])
        self.assertEqual(groups[0]["originalValues"], [{"value": 0, "count": 0}, {"value": 1, "count": 1}, {"value": 2, "count": 0}])
        self.assertEqual(groups[0]["effectiveValues"][-1]["count"], 1)
        self.assertEqual(job.result.data["conclusions"][0]["value"], 1)
        self.assertTrue(all("average" not in row for row in [*groups, *report["customerRatings"]["groups"]]))

    def test_latest_revision_is_explicit_and_pending_or_failure_has_no_previous_score(self):
        self.reply()
        event = self.complete()
        self.analyzed(event)
        repeat = request_quality_job(context=self.context, conversation_id=self.conversation.pk,
                                     completion_event_id=event.operation_id, completed_at=event.occurred_at,
                                     operation_id=uuid4(), repeat=True)
        report = self.report()["qualityAnalysis"]
        self.assertEqual(report["revisionPolicy"], "latest_per_completion")
        self.assertEqual((report["count"], report["states"]["WAITING"]), (1, 1))
        self.assertEqual(report["details"][0]["revision"], 2)
        self.assertEqual(report["groups"], [])
        start_quality_job(context=self.context, job_id=repeat.pk)
        finish_quality_job(context=self.context, job_id=repeat.pk, error_code="provider_unavailable")
        self.assertEqual(self.report()["qualityAnalysis"]["states"]["FAILED"], 1)
        self.assertEqual(self.report()["qualityAnalysis"]["groups"], [])

    def test_period_basis_boundaries_and_historical_dimensions_survive_current_changes(self):
        self.reply()
        event = self.complete()
        rating = self.rated(event)
        self.analyzed(event)
        self.conversation.group = None
        self.conversation.connection = None
        self.conversation.save(update_fields=["group", "connection"])
        report = self.report(group=self.group.pk, connection=self.connection.pk, transport="WEB")
        self.assertEqual(report["customerRatings"]["count"], 1)
        self.assertEqual(report["qualityAnalysis"]["count"], 1)
        for boundary, counts in ((event.occurred_at, (0, 0)), (rating.received_at, (0, 1))):
            filters = ReportFilters(self.start, boundary, "UTC")
            result = calculate_support_report(context=self.context, filters=filters)
            self.assertEqual((result["customerRatings"]["count"], result["qualityAnalysis"]["count"]), counts)
        filters = ReportFilters(rating.received_at, timezone.now() + timedelta(seconds=1), "UTC")
        result = calculate_support_report(context=self.context, filters=filters)
        self.assertEqual((result["customerRatings"]["count"], result["qualityAnalysis"]["count"]), (1, 0))

    def test_quality_string_and_typed_numeric_scales_are_not_coerced(self):
        for scale, value in (([1, 1.0], 1.0), (["bad", "good"], "good")):
            configure_quality(context=self.context, enabled=True, criteria=[{
                "code": "resolution", "description": "Resolution", "scale": scale,
            }])
            self.reply()
            self.analyzed(self.complete(), value=value)
        groups = sorted(self.report()["qualityAnalysis"]["groups"], key=lambda row: row["criteriaVersion"])
        self.assertEqual(groups[0]["originalValues"], [{"value": 1, "count": 0}, {"value": 1.0, "count": 1}])
        self.assertEqual(groups[1]["originalValues"], [{"value": "bad", "count": 0}, {"value": "good", "count": 1}])
