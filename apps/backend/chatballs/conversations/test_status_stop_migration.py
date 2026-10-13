"""Upgrade an actual blocked selection only in Django's isolated test database."""

from datetime import timedelta
from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class StatusStopMigrationTests(TransactionTestCase):
    def test_existing_block_instant_is_preserved_without_inventing_unblocked_stops(self):
        before = [("conversations", "0035_report_source_boundary"),
                  ("tenancy", "0046_merge_domain_event_guards"),
                  ("identity", "0044_merge_work_status_supervisor")]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(before)
        try:
            # A sibling main leaf does not roll back the report branch. The
            # shared ancestors must actually remove the stop field and trigger.
            applied = MigrationExecutor(connection).loader.applied_migrations
            self.assertNotIn(("identity", "0045_work_status_stop"), applied)
            self.assertNotIn(("tenancy", "0047_work_status_block_stop"), applied)
            apps = executor.loader.project_state(before).apps
            organization = apps.get_model("identity", "Organization").objects.create(name="Stop", slug="stop-upgrade")
            user = apps.get_model("identity", "HumanUser").objects.create(email="stop-upgrade@reports.test")
            start, block = timezone.now() - timedelta(hours=2), timezone.now() - timedelta(hours=1)
            member = apps.get_model("identity", "OrganizationMembership").objects.create(
                organization_id=organization.pk, user_id=user.pk, role="EMPLOYEE", work_status="READY",
                work_status_version=1, work_status_changed_at=start, blocked_at=block,
            )
            operations = apps.get_model("identity", "WorkStatusOperation")
            operation = operations.objects.create(organization_id=organization.pk, membership_id=member.pk,
                                                   previous_status="UNAVAILABLE", status="READY", version=1,
                                                   changed_at=start, recorded_at=start, operation_id=uuid4())
            boundary = apps.get_model("conversations", "ConversationEventHistoryStart").objects.get_or_create(pk=1)[0]
            storage_start = boundary.available_from
            deploy = timezone.now()
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            current = executor.loader.project_state(latest).apps
            migrated = current.get_model("identity", "WorkStatusOperation").objects.get(pk=operation.pk)
            self.assertEqual(migrated.stopped_at, block)
            self.assertEqual(migrated.status, "READY")
            boundaries = current.get_model("conversations", "ConversationEventHistoryStart")
            boundary = boundaries.objects.get(pk=1)
            self.assertEqual(boundary.available_from, storage_start)
            self.assertGreaterEqual(boundary.status_stops_available_from, deploy)
            source_start = boundary.status_stops_available_from
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(boundaries.objects.get(pk=1).status_stops_available_from, source_start)
        finally:
            MigrationExecutor(connection).migrate(latest)
