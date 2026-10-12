from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from chatballs.ai.models import AIAgent, AIAgentStatus


class AssistanceMigrationTests(TransactionTestCase):
    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_existing_agent_keeps_configuration_and_help_defaults_off(self):
        executor = MigrationExecutor(connection)
        previous = [("ai", "0024_agenttool"), ("tenancy", "0040_agent_tool_guards")]
        executor.migrate(previous)
        apps = executor.loader.project_state(previous).apps
        organization = apps.get_model("identity", "Organization").objects.create(
            name="Legacy", slug="assist-legacy",
        )
        channel = apps.get_model("channels", "Channel").objects.create(
            organization=organization, name="Legacy", code="assist-legacy",
        )
        agent = apps.get_model("ai", "AIAgent").objects.create(
            organization=organization, channel=channel, name="Legacy", status=AIAgentStatus.ACTIVE,
            model="existing-model", model_params={"temperature": 0.3}, instructions="Keep",
            history_limit=42, answer_language="en", lifecycle_version=7,
        )
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        migrated = AIAgent.objects.get(pk=agent.pk)
        self.assertFalse(migrated.assistance_enabled)
        self.assertEqual(migrated.status, AIAgentStatus.ACTIVE)
        self.assertEqual(migrated.model, "existing-model")
        self.assertEqual(migrated.model_params, {"temperature": 0.3})
        self.assertEqual(migrated.instructions, "Keep")
        self.assertEqual(migrated.history_limit, 42)
        self.assertEqual(migrated.answer_language, "en")
        self.assertEqual(migrated.lifecycle_version, 7)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname IN ('ai_replyassistanceattempt', 'ai_replysuggestion')"
            )
            rows = cursor.fetchall()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(enabled and forced for _name, enabled, forced in rows))
