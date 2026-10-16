"""An actual schema upgrade on the isolated test database preserves legacy data."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class TemplateMigrationTests(TransactionTestCase):
    before = [("tenancy", "0042_participant_guards")]
    after = [("tenancy", "0043_template_library_guards")]

    def test_existing_templates_become_shared_without_changing_content_or_ids(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(self.before)
        try:
            apps = executor.loader.project_state(self.before).apps
            organization = apps.get_model("identity", "Organization").objects.create(
                name="Before libraries", slug="before-libraries",
            )
            old = apps.get_model("conversations", "ReplyTemplate").objects.create(
                organization_id=organization.pk, title="Legacy {{company}}",
                text="  Hello {{ client_name }}!\n\nOriginal text.  ",
            )
            executor = MigrationExecutor(connection)
            executor.migrate(self.after)
            apps = executor.loader.project_state(self.after).apps
            migrated = apps.get_model("conversations", "ReplyTemplate").objects.get(pk=old.pk)
            for field in ("id", "organization_id", "title", "text", "created_at", "updated_at"):
                self.assertEqual(getattr(migrated, field), getattr(old, field))
            self.assertIsNone(migrated.owner_id)
            self.assertIsNone(migrated.category_id)
            self.assertEqual(migrated.tags.count(), 0)
            for model in ("ReplyTemplateCategory", "ReplyTemplateTag", "ReplyTemplateManagementGrant"):
                self.assertEqual(apps.get_model("conversations", model).objects.count(), 0)
        finally:
            MigrationExecutor(connection).migrate(latest)
