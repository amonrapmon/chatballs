"""Upgrade only the disposable Django test database."""

from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class WorkStatusMigrationTests(TransactionTestCase):
    before = [("identity", "0041_instance_tools_private_network"), ("tenancy", "0041_transfer_guards")]
    after = [("tenancy", "0042_work_status_guards")]

    def test_existing_memberships_have_no_invented_work_intervals(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(self.before)
        try:
            old_apps = executor.loader.project_state(self.before).apps
            organizations = [old_apps.get_model("identity", "Organization").objects.create(name=f"Old {i}", slug=f"old-status-{i}") for i in range(2)]
            user = old_apps.get_model("identity", "HumanUser").objects.create(email="old-status@example.test")
            membership_model = old_apps.get_model("identity", "OrganizationMembership")
            memberships = [membership_model.objects.create(organization_id=org.pk, user_id=user.pk, role="EMPLOYEE") for org in organizations]
            membership_model.objects.filter(pk__in=[m.pk for m in memberships]).update(created_at=timezone.now() - timedelta(days=365))
            executor = MigrationExecutor(connection)
            executor.migrate(self.after)
            apps = executor.loader.project_state(self.after).apps
            model = apps.get_model("identity", "OrganizationMembership")
            for membership in memberships:
                migrated = model.objects.get(pk=membership.pk)
                self.assertEqual((migrated.work_status, migrated.work_status_version, migrated.work_status_changed_at), ("UNAVAILABLE", 0, None))
                self.assertEqual((migrated.user_id, migrated.organization_id), (membership.user_id, membership.organization_id))
            self.assertEqual(apps.get_model("identity", "WorkStatusOperation").objects.count(), 0)
            # Database defaults also support inserts by existing code.
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO identity_employeeprofile (organization_id, user_id, role, position_title, phone, totp_required, created_at) VALUES (%s, %s, 'EMPLOYEE', '', '', false, now()) RETURNING work_status, work_status_version, work_status_changed_at", [organizations[0].pk, old_apps.get_model("identity", "HumanUser").objects.create(email="new-status@example.test").pk])
                self.assertEqual(cursor.fetchone(), ("UNAVAILABLE", 0, None))
        finally:
            MigrationExecutor(connection).migrate(latest)
