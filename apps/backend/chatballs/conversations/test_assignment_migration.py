"""Upgrade existing assignments without reconstructing transfers or facts."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class AssignmentMigrationTests(TransactionTestCase):
    before = [("tenancy", "0045_merge_domain_events_work_status_supervision")]
    after = [("conversations", "0034_initial_assignment_policy")]

    def test_upgrade_preserves_assignment_and_trigger_versions_later_changes(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(self.before)
        try:
            apps = executor.loader.project_state(self.before).apps
            organization = apps.get_model("identity", "Organization").objects.create(name="Existing", slug="old-assignment")
            user = apps.get_model("identity", "HumanUser").objects.create(email="old@assignment.test")
            apps.get_model("identity", "OrganizationMembership").objects.create(
                organization=organization, user=user, role="OWNER",
            )
            channel = apps.get_model("channels", "Channel").objects.create(organization=organization, name="Old", code="old")
            contact = apps.get_model("conversations", "Contact").objects.create(organization=organization, name="Old")
            old = apps.get_model("conversations", "Conversation").objects.create(
                organization=organization, channel=channel, contact=contact, assigned_operator_id=user.pk,
            )
            executor = MigrationExecutor(connection)
            intermediate = [("tenancy", "0046_assignment_transfer_guards")]
            executor.migrate(intermediate)
            intermediate_apps = executor.loader.project_state(intermediate).apps
            custom_org = intermediate_apps.get_model("identity", "Organization").objects.create(
                name="Custom", slug="custom-assignment",
            )
            intermediate_apps.get_model("conversations", "AssignmentPolicy").objects.create(
                organization_id=custom_org.pk, ready=True, busy=False,
                break_allowed=False, unavailable=False,
            )
            executor = MigrationExecutor(connection)
            executor.migrate(self.after)
            apps = executor.loader.project_state(self.after).apps
            model = apps.get_model("conversations", "Conversation")
            current = model.objects.get(pk=old.pk)
            self.assertEqual((current.assigned_operator_id, current.assignment_version), (user.pk, 0))
            self.assertFalse(apps.get_model("conversations", "ConversationTransfer").objects.exists())
            self.assertFalse(apps.get_model("conversations", "ConversationEvent").objects.exists())
            policy = apps.get_model("conversations", "AssignmentPolicy").objects.get(organization_id=organization.pk)
            self.assertTrue(all(getattr(policy, field) for field in
                                ("ready", "busy", "break_allowed", "unavailable")))
            custom = apps.get_model("conversations", "AssignmentPolicy").objects.get(organization_id=custom_org.pk)
            self.assertEqual((custom.ready, custom.busy, custom.break_allowed, custom.unavailable),
                             (True, False, False, False))
            model.objects.filter(pk=old.pk).update(assigned_operator_id=None, assignment_version=0)
            current.refresh_from_db()
            self.assertEqual(current.assignment_version, 1)
            with connection.cursor() as cursor:
                cursor.execute("SELECT relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner) "
                               "FROM pg_class WHERE relname='conversations_assignmentpolicy'")
                self.assertEqual(cursor.fetchone(), (True, True, "chatballs_schema"))
        finally:
            MigrationExecutor(connection).migrate(latest)
