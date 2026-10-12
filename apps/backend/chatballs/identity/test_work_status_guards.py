from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from chatballs.identity.models import OrganizationMembership
from chatballs.identity.work_status_codes import WorkStatus
from chatballs.identity.work_status_models import WorkStatusOperation
from chatballs.identity.work_status_testing import WorkStatusTestBase
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


class WorkStatusGuardTests(WorkStatusTestBase):
    @staticmethod
    def app_role():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE chatballs_runtime_app")

    def row(self, **changes):
        now = timezone.now()
        return WorkStatusOperation(**{
            "organization_id": self.organization.pk, "membership_id": self.membership.pk,
            "operation_id": uuid4(), "status": WorkStatus.READY,
            "previous_status": WorkStatus.UNAVAILABLE, "version": 1,
            "changed_at": now, "recorded_at": now, **changes,
        })

    def test_cross_tenant_relations_are_guarded_in_model_and_database(self):
        with self.assertRaises(ValidationError):
            self.row(membership_id=self.other.pk).save()
        for changes in ({"membership_id": self.other.pk}, {"organization_id": self.foreign.pk}):
            with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                WorkStatusOperation.objects.bulk_create([self.row(**changes)])
        row = self.row()
        row.save()
        with self.assertRaises(DatabaseError), transaction.atomic():
            WorkStatusOperation.objects.filter(pk=row.pk).update(membership_id=self.other.pk)

    def test_invalid_status_and_initial_state_cannot_bypass_service(self):
        for changes in ({"work_status": "ONLINE"}, {"work_status": WorkStatus.READY}, {"work_status_version": 1}):
            with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                OrganizationMembership.objects.filter(pk=self.membership.pk).update(**changes)
        for changes in ({"status": "ONLINE"}, {"previous_status": "ONLINE"}, {"changed_at": None}, {"version": 0}):
            with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                WorkStatusOperation.objects.bulk_create([self.row(**changes)])

    def test_runtime_is_fail_closed_scoped_and_history_is_append_only(self):
        first = self.change()
        foreign = self.change(context=TenantContext.for_membership(self.other))
        with transaction.atomic():
            self.app_role()
            self.assertFalse(WorkStatusOperation.objects.exists())
        with tenant_atomic(self.context):
            self.app_role()
            self.assertEqual(list(WorkStatusOperation.objects.values_list("pk", flat=True)), [first.pk])
            self.assertFalse(WorkStatusOperation.objects.filter(pk=foreign.pk).exists())
            # Service also works with actual app privileges.
            self.change(WorkStatus.BREAK, 1)
            for action in (
                lambda: WorkStatusOperation.objects.bulk_create([self.row(organization_id=self.foreign.pk, membership_id=self.other.pk)]),
                lambda: WorkStatusOperation.objects.filter(pk=first.pk).update(status=WorkStatus.BUSY),
                lambda: WorkStatusOperation.objects.filter(pk=first.pk).delete(),
            ):
                with self.assertRaises(DatabaseError), transaction.atomic():
                    action()

    def test_forced_rls_and_runtime_privileges(self):
        table = WorkStatusOperation._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute("SELECT relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner) FROM pg_class WHERE relname = %s", [table])
            self.assertEqual(cursor.fetchone(), (True, True, "chatballs_schema"))
            for role, privilege, expected in (
                ("chatballs_runtime_platform", "SELECT", False),
                ("chatballs_runtime_app", "SELECT", True),
                ("chatballs_runtime_app", "INSERT", True),
                ("chatballs_runtime_app", "UPDATE", False),
                ("chatballs_runtime_app", "DELETE", False),
            ):
                cursor.execute("SELECT has_table_privilege(%s, %s, %s)", [role, table, privilege])
                self.assertEqual(cursor.fetchone()[0], expected)
