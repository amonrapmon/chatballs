from django.db import DatabaseError, transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from chatballs.identity.models import EmployeeRole
from chatballs.tenancy.context import TenantContext

from .corrections import append_quality_correction
from .models import QualityCorrection, QualityJob, QualityJobOperation
from .test_base import QualityTestBase


class ResultTests(QualityTestBase):
    def correction(self, result, **changes):
        return append_quality_correction(**{
            "context": self.context, "result_id": result.pk, "expected_revision": 0,
            "criterion_code": "resolution", "value": 2, "reason": "Reviewed messages",
            **changes,
        })

    def test_corrections_keep_author_server_time_reason_and_original(self):
        result = self.result()
        first = self.correction(result)
        admin = TenantContext.for_membership(self.members[EmployeeRole.ADMIN])
        second = self.correction(result, context=admin, expected_revision=1, value=0, reason="New evidence")
        self.assertEqual(first.author_id, self.context.membership.pk)
        self.assertEqual(second.author_id, admin.membership.pk)
        self.assertIsNotNone(first.created_at)
        self.assertGreaterEqual(second.created_at, first.created_at)
        self.assertEqual(first.reason, "Reviewed messages")
        self.assertEqual(second.reason, "New evidence")
        self.assertEqual(first.result_id, result.pk)
        self.assertEqual(list(result.corrections.values_list("revision", "value")), [(1, 2), (2, 0)])
        result.refresh_from_db()
        self.assertEqual(result.data, {"resolution": 1})

    def test_stale_revision_invalid_scale_and_blank_reason_do_not_overwrite(self):
        result = self.result()
        self.correction(result)
        for changes in ({}, {"expected_revision": 1, "value": 99},
                        {"expected_revision": 1, "criterion_code": "missing"},
                        {"expected_revision": 1, "criterion_code": []},
                        {"expected_revision": 1, "value": True},
                        {"expected_revision": 1, "reason": "  "}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.correction(result, **changes)
        self.assertEqual(result.corrections.count(), 1)

    def test_original_criteria_snapshot_result_and_corrections_are_immutable_in_sql(self):
        result = self.result()
        correction = self.correction(result)
        for row, changes in (
            (result, {"data": {"resolution": 0}}),
            (result.job.criteria_version, {"criteria": []}),
            (correction, {"reason": "Overwritten"}),
            (result.job, {"history_snapshot": [{"id": 999}]}),
            (result.job, {"state": "RUNNING"}),
            (QualityJobOperation.objects.get(job=result.job), {"job_id": 999}),
        ):
            with self.subTest(model=type(row).__name__, changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                type(row).objects.filter(pk=row.pk).update(**changes)
        for row in (result, correction, result.job.criteria_version):
            with self.subTest(delete=type(row).__name__), self.assertRaises(DatabaseError), transaction.atomic():
                # Direct SQL also covers deletion without Django's PROTECT collector.
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute(f'DELETE FROM "{row._meta.db_table}" WHERE id = %s', [row.pk])
        result.refresh_from_db()
        self.assertEqual(result.data, {"resolution": 1})

    def test_correction_access_is_tenant_scoped_and_deny_by_default(self):
        result = self.result()
        with self.assertRaises(NotFound):
            self.correction(result, context=self.foreign_context)
        with self.assertRaises(PermissionDenied):
            self.correction(result, context=TenantContext.for_membership(self.members[EmployeeRole.EMPLOYEE]))
        self.assertEqual(QualityCorrection.objects.count(), 0)
        self.assertEqual(QualityJob.objects.count(), 1)
