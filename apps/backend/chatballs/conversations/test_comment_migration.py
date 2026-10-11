"""Upgrade the isolated test database; do not backfill invented history."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class CommentMigrationTests(TransactionTestCase):
    before = [("tenancy", "0041_transfer_guards"), ("conversations", "0030_transfer_data")]
    after = [("tenancy", "0042_comment_guards")]

    def test_existing_note_and_customer_messages_survive_without_comments(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(self.before)
        try:
            old = executor.loader.project_state(self.before).apps
            organization = old.get_model("identity", "Organization").objects.create(
                name="Before comments", slug="before-comments"
            )
            author = old.get_model("identity", "HumanUser").objects.create(email="old@comments.test")
            old.get_model("identity", "OrganizationMembership").objects.create(
                organization_id=organization.pk, user_id=author.pk, role="OWNER"
            )
            channel = old.get_model("channels", "Channel").objects.create(
                organization_id=organization.pk, code="old", name="Old"
            )
            contact = old.get_model("conversations", "Contact").objects.create(
                organization_id=organization.pk, name="Customer"
            )
            conversation = old.get_model("conversations", "Conversation").objects.create(
                organization_id=organization.pk, channel_id=channel.pk, contact_id=contact.pk,
                note="Original mutable note", note_author_id=author.pk, note_updated_at=timezone.now(),
            )
            message = old.get_model("conversations", "Message").objects.create(
                organization_id=organization.pk, conversation_id=conversation.pk,
                author_type="CONTACT", text="Existing customer message",
            )
            conversation_snapshot = old.get_model("conversations", "Conversation").objects.values().get(pk=conversation.pk)
            message_snapshot = old.get_model("conversations", "Message").objects.values().get(pk=message.pk)
            executor = MigrationExecutor(connection)
            executor.migrate(self.after)
            new = executor.loader.project_state(self.after).apps
            self.assertEqual(new.get_model("conversations", "ConversationComment").objects.count(), 0)
            self.assertEqual(new.get_model("conversations", "Conversation").objects.values().get(pk=conversation.pk), conversation_snapshot)
            self.assertEqual(new.get_model("conversations", "Message").objects.values().get(pk=message.pk), message_snapshot)
        finally:
            MigrationExecutor(connection).migrate(latest)
