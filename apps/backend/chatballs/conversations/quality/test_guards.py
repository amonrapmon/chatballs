from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction

from chatballs.tenancy.database import tenant_atomic

from .corrections import append_quality_correction
from .jobs import finish_quality_job, start_quality_job
from .models import (
    QualityCorrection,
    QualityCriteriaVersion,
    QualityJob,
    QualityJobOperation,
    QualityResult,
    QualitySettings,
)
from .test_base import CRITERIA, QualityTestBase


class GuardTests(QualityTestBase):
    def test_services_execute_with_real_runtime_role_and_tenant_context(self):
        with tenant_atomic(self.context):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            self.configure()
            self.message()
            job = self.job()
            self.assertTrue(start_quality_job(context=self.context, job_id=job.pk))
            finish_quality_job(context=self.context, job_id=job.pk, validated_result={"resolution": 1})
            result = job.result
            correction = append_quality_correction(
                context=self.context, result_id=result.pk, expected_revision=0,
                criterion_code="resolution", value=2, reason="Runtime review",
            )
            self.assertEqual(correction.author_id, self.context.membership_id)
            self.assertEqual(result.data, {"resolution": 1})
            with self.assertRaises(DatabaseError), transaction.atomic():
                QualityResult.objects.filter(pk=result.pk).update(data={"resolution": 0})

    def foreign_rows(self, result):
        return [
            QualityCriteriaVersion(organization=self.organization, version=2, criteria=CRITERIA, created_by=self.foreign_member),
            QualitySettings(organization=self.foreign, current_version=result.job.criteria_version),
            QualityJob(organization=self.organization, conversation=self.foreign_conversation,
                       criteria_version=result.job.criteria_version, completion_event_id=uuid4(),
                       completed_at=result.job.completed_at, history_revision="a" * 64, history_snapshot=[],
                       operation_id=uuid4(), revision=1),
            QualityJob(organization=self.foreign, conversation=self.foreign_conversation,
                       criteria_version=result.job.criteria_version, completion_event_id=uuid4(),
                       completed_at=result.job.completed_at, history_revision="a" * 64, history_snapshot=[],
                       operation_id=uuid4(), revision=1),
            QualityResult(organization=self.foreign, job=result.job, data={"score": 1}),
            QualityJobOperation(organization=self.foreign, job=result.job, operation_id=uuid4()),
            QualityCorrection(organization=self.organization, result=result, author=self.foreign_member,
                              reason="Foreign author", revision=1, criterion_code="resolution", value=1),
            QualityCorrection(organization=self.foreign, result=result, author=self.foreign_member,
                              reason="Foreign result", revision=1, criterion_code="resolution", value=1),
        ]

    def test_cross_tenant_relations_rejected_by_model_and_bulk_sql(self):
        result = self.result()
        for row in self.foreign_rows(result):
            with self.subTest(model=type(row).__name__), self.assertRaises(ValidationError):
                row.save()
            with self.subTest(bulk=type(row).__name__), self.assertRaises(DatabaseError), transaction.atomic():
                type(row).objects.bulk_create([row])

    def test_rls_fail_closed_and_runtime_cannot_read_or_write_foreign_data(self):
        result = self.result()
        QualityCorrection.objects.create(
            organization=self.organization, result=result, author=self.context.membership,
            reason="Reviewed", revision=1, criterion_code="resolution", value=2,
        )
        models = (QualitySettings, QualityCriteriaVersion, QualityJob, QualityResult, QualityCorrection, QualityJobOperation)
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            for model in models:
                self.assertEqual(model.objects.count(), 0)
        with tenant_atomic(self.context):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            for model in models:
                self.assertEqual(model.objects.count(), 1)
            for row in self.foreign_rows(result):
                with self.subTest(model=type(row).__name__), self.assertRaises(DatabaseError), transaction.atomic():
                    type(row).objects.bulk_create([row])
        with tenant_atomic(self.foreign_context):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            for model in models:
                self.assertEqual(model.objects.count(), 0)
                self.assertEqual(model.objects.filter(pk=result.pk).delete()[0], 0)

    def test_all_quality_tables_have_forced_rls_and_no_platform_access(self):
        tables = [model._meta.db_table for model in (
            QualitySettings, QualityCriteriaVersion, QualityJob, QualityResult, QualityCorrection, QualityJobOperation,
        )]
        with connection.cursor() as cursor:
            cursor.execute("SELECT relname, relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner) "
                           "FROM pg_class WHERE relname = ANY(%s)", [tables])
            rows = cursor.fetchall()
            self.assertEqual(len(rows), len(tables))
            self.assertTrue(all(enabled and forced and owner == "chatballs_schema" for _, enabled, forced, owner in rows))
            for table in tables:
                cursor.execute("SELECT has_table_privilege('chatballs_runtime_platform', %s, 'SELECT')", [table])
                self.assertFalse(cursor.fetchone()[0])
