from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import HumanUser, Organization, OrganizationMembership
from chatballs.identity.supervision_models import EmployeeGroupSupervision
from chatballs.tenancy.database import tenant_atomic


class SupervisionDataTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Data", slug="supervision-data")
        self.other = Organization.objects.create(name="Other", slug="supervision-data-other")
        self.group = EmployeeGroup.objects.create(organization=self.org, name="Control")
        self.foreign = EmployeeGroup.objects.create(organization=self.other, name="Foreign")
        user = HumanUser.objects.create_user(email="data@supervision.test")
        self.member = OrganizationMembership.objects.create(
            user=user, organization=self.org, role="SUPERVISOR"
        )

    def test_model_and_database_reject_cross_tenant_links_and_duplicates(self):
        with self.assertRaises(ValidationError):
            EmployeeGroupSupervision.objects.create(employee=self.member, group=self.foreign)
        with self.assertRaises(DatabaseError), transaction.atomic():
            EmployeeGroupSupervision.objects.bulk_create([
                EmployeeGroupSupervision(
                    organization=self.org, employee=self.member, group=self.foreign
                )
            ])
        EmployeeGroupSupervision.objects.create(employee=self.member, group=self.group)
        with self.assertRaises(DatabaseError), transaction.atomic():
            EmployeeGroupSupervision.objects.create(employee=self.member, group=self.group)
        with self.assertRaises(DatabaseError), transaction.atomic():
            EmployeeGroupSupervision.objects.filter(employee=self.member).update(group=self.foreign)

    def test_runtime_rls_is_fail_closed_and_tenant_scoped(self):
        link = EmployeeGroupSupervision.objects.create(employee=self.member, group=self.group)
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            try:
                self.assertEqual(EmployeeGroupSupervision.objects.count(), 0)
            finally:
                cursor.execute("RESET ROLE")
        for org, expected_ids in ((self.org, [link.id]), (self.other, [])):
            with tenant_atomic(org.id), connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
                try:
                    self.assertEqual(
                        list(EmployeeGroupSupervision.objects.values_list("id", flat=True)),
                        expected_ids,
                    )
                finally:
                    cursor.execute("RESET ROLE")
        with self.assertRaises(DatabaseError), tenant_atomic(self.other.id):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
                EmployeeGroupSupervision.objects.bulk_create([
                    EmployeeGroupSupervision(
                        organization=self.org, employee=self.member, group=self.group
                    )
                ])


class SupervisionMigrationTests(TransactionTestCase):
    def test_migration_preserves_roles_memberships_and_groups_without_assigning_supervisors(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [("identity", "0042_organization_participant_limit"), ("tenancy", "0042_participant_guards")]
        try:
            executor.migrate(before)
            apps = executor.loader.project_state(before).apps
            org = apps.get_model("identity", "Organization").objects.create(name="Migration", slug="supervision-migration")
            group = apps.get_model("identity", "EmployeeGroup").objects.create(organization=org, name="Existing")
            memberships = apps.get_model("identity", "OrganizationMembership")
            group_members = apps.get_model("identity", "EmployeeGroupMember")
            roles = {}
            for role in ("OWNER", "ADMIN", "EMPLOYEE"):
                user = apps.get_model("identity", "HumanUser").objects.create(email=f"{role}@migration.test")
                member = memberships.objects.create(organization=org, user=user, role=role)
                roles[member.id] = role
                group_members.objects.create(organization=org, employee=member, group=group)
            links = list(group_members.objects.values_list("id", "employee_id", "group_id"))
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            self.assertEqual(dict(apps.get_model("identity", "OrganizationMembership").objects.values_list("id", "role")), roles)
            self.assertEqual(list(apps.get_model("identity", "EmployeeGroupMember").objects.values_list("id", "employee_id", "group_id")), links)
            self.assertEqual(apps.get_model("identity", "EmployeeGroupSupervision").objects.count(), 0)
        finally:
            MigrationExecutor(connection).migrate(latest)
