"""Upgrade and rollback on the isolated test database, preserving WEB context."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class EmailContinuationMigrationTests(TransactionTestCase):
    before = [("tenancy", "0042_participant_guards"), ("conversations", "0031_participant_data")]
    after = [("tenancy", "0043_email_continuation_guards")]

    def test_upgrade_and_rollback_preserve_original_web_context_and_messages(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(self.before)
        try:
            old = executor.loader.project_state(self.before).apps
            organization = old.get_model("identity", "Organization").objects.create(name="Before mail", slug="before-mail")
            user = old.get_model("identity", "HumanUser").objects.create(email="before@mail-data.test")
            old.get_model("identity", "OrganizationMembership").objects.create(
                organization_id=organization.pk, user_id=user.pk, role="OWNER",
            )
            group = old.get_model("identity", "EmployeeGroup").objects.create(organization_id=organization.pk, name="Web group")
            channel = old.get_model("channels", "Channel").objects.create(organization_id=organization.pk, code="web", name="Web")
            agent = old.get_model("ai", "AIAgent").objects.create(organization_id=organization.pk, channel_id=channel.pk)
            web = old.get_model("integrations", "Integration").objects.create(
                organization_id=organization.pk, kind="MESSENGER", provider="WEB", name="Web", channel_id=channel.pk,
            )
            contact = old.get_model("conversations", "Contact").objects.create(
                organization_id=organization.pk, email="visitor@mail-data.test",
            )
            conversation_model = old.get_model("conversations", "Conversation")
            conversation = conversation_model.objects.create(
                organization_id=organization.pk, channel_id=channel.pk, connection_id=web.pk,
                contact_id=contact.pk, group_id=group.pk, assigned_operator_id=user.pk,
                external_chat_id="web-session", transport_meta={"source": "website"},
            )
            message = old.get_model("conversations", "Message").objects.create(
                organization_id=organization.pk, conversation_id=conversation.pk, author_type="CONTACT", text="Question",
            )
            original = conversation_model.objects.filter(pk=conversation.pk).values().get()
            executor = MigrationExecutor(connection)
            executor.migrate(self.after)
            new = executor.loader.project_state(self.after).apps
            self.assertEqual(new.get_model("conversations", "Conversation").objects.filter(pk=conversation.pk).values().get(), original)
            self.assertTrue(new.get_model("ai", "AIAgent").objects.filter(pk=agent.pk, channel_id=channel.pk).exists())
            for name in ("EmailThread", "EmailThreadMessage", "EmailSendOperation", "EmailSendAttempt"):
                self.assertEqual(new.get_model("conversations", name).objects.count(), 0)
            executor = MigrationExecutor(connection)
            executor.migrate(self.before)
            self.assertEqual(conversation_model.objects.filter(pk=conversation.pk).values().get(), original)
            self.assertEqual(old.get_model("conversations", "Message").objects.get(pk=message.pk).text, "Question")
        finally:
            MigrationExecutor(connection).migrate(latest)
