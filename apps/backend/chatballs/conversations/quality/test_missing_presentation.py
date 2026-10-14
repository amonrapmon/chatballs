"""An unscored conclusion remains reviewable with the scale-index contract."""

from .corrections import append_quality_correction
from .jobs import finish_quality_job, start_quality_job
from .presentation import job_payload
from .test_base import QualityTestBase


class MissingPresentationTests(QualityTestBase):
    def test_unscored_conclusion_has_no_index_until_corrected(self):
        self.configure()
        job = self.job()
        start_quality_job(context=self.context, job_id=job.pk)
        finish_quality_job(context=self.context, job_id=job.pk, validated_result={"conclusions": [
            {"code": "resolution", "value": None, "missingReason": "insufficient_messages",
             "explanation": "No public evidence", "recommendations": [], "messageIds": []},
        ]})
        conclusion = job_payload(job, self.context)["conclusions"][0]
        self.assertIsNone(conclusion["originalValue"])
        self.assertIsNone(conclusion["effectiveValue"])
        self.assertIsNone(conclusion["effectiveScaleIndex"])
        self.assertEqual(conclusion["missingReason"], "insufficient_messages")

        append_quality_correction(context=self.context, result_id=job.result.pk, expected_revision=0,
                                  criterion_code="resolution", value=0, reason="Reviewed public evidence")
        conclusion = job_payload(job, self.context)["conclusions"][0]
        self.assertIsNone(conclusion["originalValue"])
        self.assertEqual(conclusion["effectiveValue"], 0)
        self.assertEqual(conclusion["effectiveScaleIndex"], 0)
        self.assertEqual(conclusion["missingReason"], "insufficient_messages")
