"""Exercise upgrade and reversal exclusively in Django's disposable test DB."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class DomainEventMigrationTests(TransactionTestCase):
    before = [("tenancy", "0042_participant_guards"), ("conversations", "0031_participant_data")]
    after = [("tenancy", "0043_domain_event_guards")]

    def test_upgrade_records_boundary_without_inventing_old_facts(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(self.before)
        try:
            old_apps = executor.loader.project_state(self.before).apps
            organization = old_apps.get_model("identity", "Organization").objects.create(
                name="Existing", slug="existing-facts"
            )
            channel = old_apps.get_model("channels", "Channel").objects.create(
                organization_id=organization.pk, code="existing", name="Existing"
            )
            contact = old_apps.get_model("conversations", "Contact").objects.create(
                organization_id=organization.pk, name="Existing customer"
            )
            conversation = old_apps.get_model("conversations", "Conversation").objects.create(
                organization_id=organization.pk, channel_id=channel.pk,
                contact_id=contact.pk, lifecycle="CLOSED", control_mode="HUMAN",
            )
            before_upgrade = timezone.now()
            executor = MigrationExecutor(connection)
            executor.migrate(self.after)
            apps = executor.loader.project_state(self.after).apps
            event = apps.get_model("conversations", "ConversationEvent")
            boundary_model = apps.get_model("conversations", "ConversationEventHistoryStart")
            boundary = boundary_model.objects.get(pk=1)
            self.assertEqual(boundary_model.objects.count(), 1)
            self.assertLessEqual(before_upgrade, boundary.available_from)
            self.assertLessEqual(boundary.available_from, timezone.now())
            self.assertEqual(event.objects.count(), 0)
            migrated = apps.get_model("conversations", "Conversation").objects.get(pk=conversation.pk)
            self.assertEqual((migrated.lifecycle, migrated.control_mode), ("CLOSED", "HUMAN"))
            self.assertLess(migrated.created_at, boundary.available_from)
            MigrationExecutor(connection).migrate(self.after)
            self.assertEqual(boundary_model.objects.get(pk=1).available_from, boundary.available_from)
        finally:
            MigrationExecutor(connection).migrate(latest)
