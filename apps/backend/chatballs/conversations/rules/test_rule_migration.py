"""Exercise the upgrade exclusively in Django's disposable test DB."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class HandlingRuleMigrationTests(TransactionTestCase):
    before = [
        ("tenancy", "0044_merge_domain_event_and_diagnostic_guards"),
        ("conversations", "0032_domain_event_data"),
    ]
    after = [("tenancy", "0045_handling_rule_guards")]

    def test_upgrade_keeps_queue_delays_and_enables_no_customer_messages(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        executor.migrate(self.before)
        try:
            old_apps = executor.loader.project_state(self.before).apps
            organizations = old_apps.get_model("identity", "Organization").objects
            tuned = organizations.create(name="Tuned", slug="tuned-queue")
            untouched = organizations.create(name="Untouched", slug="untouched-queue")
            old_apps.get_model("conversations", "QueueEscalationPolicy").objects.create(
                organization_id=tuned.pk, remind_after_minutes=2, widen_after_minutes=4,
                escalate_after_minutes=8, assignment_timeout_minutes=25,
            )
            executor = MigrationExecutor(connection)
            executor.migrate(self.after)
            apps = executor.loader.project_state(self.after).apps
            rules = apps.get_model("conversations", "HandlingRule").objects
            self.assertEqual(
                set(rules.values_list("organization_id", "kind", "enabled", "version", "delay_minutes")),
                {
                    (tuned.pk, "ASSIGNMENT_RETURN", True, 1, 25),
                    # Порогов ещё не трогали — действует обычный срок.
                    (untouched.pk, "ASSIGNMENT_RETURN", True, 1, 10),
                },
            )
            for rule in rules.all():
                self.assertEqual((rule.recipients, rule.conditions), (["CONVERSATION_GROUP"], {}))
            policy = apps.get_model("conversations", "QueueEscalationPolicy").objects.get()
            self.assertEqual(
                (policy.organization_id, policy.remind_after_minutes, policy.widen_after_minutes,
                 policy.escalate_after_minutes, policy.assignment_timeout_minutes),
                (tuned.pk, 2, 4, 8, 25),
            )
            self.assertEqual(apps.get_model("conversations", "RuleExecution").objects.count(), 0)
            # Повторный migrate ничего не добавляет.
            MigrationExecutor(connection).migrate(self.after)
            self.assertEqual(rules.count(), 2)
        finally:
            MigrationExecutor(connection).migrate(latest)
