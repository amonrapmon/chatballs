"""Additive schema change preserves existing routes, shared links and history."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from chatballs.ai.models import AIAgent
from chatballs.channels.models import Channel
from chatballs.conversations.models import Contact, Conversation, Message
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import Organization
from chatballs.integrations.models import Integration
from chatballs.webchat.testing import create_web_widget


class OperationModeMigrationTests(TransactionTestCase):
    def test_existing_data_survives_additive_migration(self):
        organization = Organization.objects.create(name="Existing", slug="existing-mode")
        group = EmployeeGroup.objects.create(organization=organization, name="Team")
        channel = Channel.objects.create(organization=organization, code="existing", name="Existing", group=group)
        agent = AIAgent.objects.create(channel=channel, name="Agent")
        widget = create_web_widget(channel, allowed_origins=["https://example.com"])
        other = Integration.objects.create(organization=organization, name="Shared", provider="TELEGRAM", kind="MESSENGER", channel=channel)
        contact = Contact.objects.create(organization=organization, name="Customer")
        conversation = Conversation.objects.create(organization=organization, channel=channel, connection=other, contact=contact, group=group)
        message = Message.objects.create(conversation=conversation, author_type="CONTACT", text="History")
        snapshot = (agent.pk, other.pk, widget.integration_id, widget.public_key, channel.pk, group.pk, conversation.pk, message.pk)
        executor = MigrationExecutor(connection)
        executor.migrate([("identity", "0047_merge_rule_actions_main")])
        try:
            executor = MigrationExecutor(connection)
            historical = executor.loader.project_state([("identity", "0047_merge_rule_actions_main")]).apps
            old_organization = historical.get_model("identity", "Organization").objects.get(pk=organization.pk)
            self.assertFalse(hasattr(old_organization, "operation_mode"))
        finally:
            MigrationExecutor(connection).migrate([("identity", "0048_organization_operation_mode")])
        organization.refresh_from_db()
        agent.refresh_from_db()
        widget.refresh_from_db()
        channel.refresh_from_db()
        conversation.refresh_from_db()
        message.refresh_from_db()
        self.assertEqual(organization.operation_mode, "AI_AGENTS")
        self.assertEqual(organization.operation_mode_version, 1)
        self.assertEqual(snapshot, (agent.pk, other.pk, widget.integration_id, widget.public_key, channel.pk, group.pk, conversation.pk, message.pk))
        self.assertEqual(channel.connections.count(), 2)
        self.assertEqual(agent.channel_id, channel.pk)
        self.assertEqual(channel.group_id, group.pk)
        self.assertEqual(conversation.group_id, group.pk)
        self.assertEqual(message.text, "History")
