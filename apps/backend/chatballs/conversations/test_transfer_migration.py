"""Upgrade a pre-transfer schema in the isolated Django test database only."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class TransferMigrationTests(TransactionTestCase):
    before = [("tenancy", "0040_agent_tool_guards"), ("conversations", "0029_tool_called_event")]
    after = [("tenancy", "0041_transfer_guards")]

    def test_existing_assignment_survives_without_invented_history(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(self.before)
        try:
            old_apps = executor.loader.project_state(self.before).apps
            organization = old_apps.get_model("identity", "Organization").objects.create(
                name="Before transfers", slug="before-transfers"
            )
            user = old_apps.get_model("identity", "HumanUser").objects.create(email="old@transfers.test")
            old_apps.get_model("identity", "OrganizationMembership").objects.create(
                organization_id=organization.pk, user_id=user.pk, role="OWNER"
            )
            channel = old_apps.get_model("channels", "Channel").objects.create(
                organization_id=organization.pk, code="old", name="Old"
            )
            contact = old_apps.get_model("conversations", "Contact").objects.create(
                organization_id=organization.pk, name="Customer"
            )
            conversation = old_apps.get_model("conversations", "Conversation").objects.create(
                organization_id=organization.pk, channel_id=channel.pk,
                contact_id=contact.pk, assigned_operator_id=user.pk,
            )
            executor = MigrationExecutor(connection)
            executor.migrate(self.after)
            apps = executor.loader.project_state(self.after).apps
            migrated = apps.get_model("conversations", "Conversation").objects.get(pk=conversation.pk)
            self.assertEqual(migrated.assigned_operator_id, user.pk)
            self.assertEqual(apps.get_model("conversations", "ConversationTransfer").objects.count(), 0)
            self.assertEqual(apps.get_model("conversations", "TransferReason").objects.count(), 0)
        finally:
            MigrationExecutor(connection).migrate(latest)
