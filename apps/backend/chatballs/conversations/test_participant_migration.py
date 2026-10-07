"""Check an upgrade on the isolated Django test database, never on demo accounts."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class ParticipantMigrationTests(TransactionTestCase):
    before = [
        ("tenancy", "0041_transfer_guards"),
        ("conversations", "0030_transfer_data"),
        ("identity", "0041_instance_tools_private_network"),
    ]
    after = [("tenancy", "0042_participant_guards")]

    def test_upgrade_preserves_assignments_and_starts_without_participants(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(self.before)
        try:
            old_apps = executor.loader.project_state(self.before).apps
            organization = old_apps.get_model("identity", "Organization").objects.create(
                name="Before participation", slug="before-participation",
            )
            user = old_apps.get_model("identity", "HumanUser").objects.create(email="old@participation.test")
            old_apps.get_model("identity", "OrganizationMembership").objects.create(
                organization_id=organization.pk, user_id=user.pk, role="OWNER",
            )
            channel = old_apps.get_model("channels", "Channel").objects.create(
                organization_id=organization.pk, code="old", name="Old",
            )
            contact = old_apps.get_model("conversations", "Contact").objects.create(
                organization_id=organization.pk, name="Customer",
            )
            assigned_at = timezone.now()
            assigned = old_apps.get_model("conversations", "Conversation").objects.create(
                organization_id=organization.pk, channel_id=channel.pk, contact_id=contact.pk,
                assigned_operator_id=user.pk, assigned_at=assigned_at, control_mode="HUMAN",
            )
            unassigned = old_apps.get_model("conversations", "Conversation").objects.create(
                organization_id=organization.pk, channel_id=channel.pk, contact_id=contact.pk,
            )
            executor = MigrationExecutor(connection)
            executor.migrate(self.after)
            apps = executor.loader.project_state(self.after).apps
            conversation_model = apps.get_model("conversations", "Conversation")
            migrated = conversation_model.objects.get(pk=assigned.pk)
            self.assertEqual(migrated.assigned_operator_id, user.pk)
            self.assertEqual(migrated.assigned_at, assigned_at)
            self.assertEqual(migrated.control_mode, "HUMAN")
            self.assertIsNone(conversation_model.objects.get(pk=unassigned.pk).assigned_operator_id)
            self.assertEqual(apps.get_model("conversations", "ConversationParticipant").objects.count(), 0)
            self.assertEqual(apps.get_model("identity", "Organization").objects.get(
                pk=organization.pk,
            ).additional_participant_limit, 5)
        finally:
            MigrationExecutor(connection).migrate(latest)
