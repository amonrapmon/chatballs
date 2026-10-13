"""Настройка правила: своё включение, версия и только то, что есть в каталоге."""

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.exceptions import PermissionDenied, ValidationError

from chatballs.conversations.queue_models import QueueEscalationPolicy, policy_for
from chatballs.conversations.rules.models import (
    HandlingRule,
    HandlingRuleKind,
    RuleAction,
    RuleExecution,
    RuleRecipient,
)
from chatballs.conversations.rules.rule_test_base import RuleScene
from chatballs.conversations.rules.settings import rule_for, update_rule
from chatballs.testing import TenantAPIClient, tenant_context_for

RETURN = HandlingRuleKind.ASSIGNMENT_RETURN


class RuleSettingsTests(RuleScene, TestCase):
    def change(self, changes: dict, kind: str = RETURN, context=None) -> HandlingRule:
        return update_rule(context=context or self.context, kind=kind, changes=changes)

    def test_every_rule_is_a_separate_row_with_its_own_switch_and_version(self) -> None:
        QueueEscalationPolicy.objects.create(
            organization=self.organization, assignment_timeout_minutes=7
        )
        rules = {kind: rule_for(self.organization.pk, kind) for kind in HandlingRuleKind.values}
        self.assertEqual(len({rule.pk for rule in rules.values()}), 4)
        returning = rules[RETURN]
        self.assertEqual(
            (returning.enabled, returning.version, returning.delay_minutes,
             returning.conditions, returning.recipients),
            (True, 1, 7, {}, [RuleRecipient.CONVERSATION_GROUP]),
        )
        # Ни одно новое правило, включая сообщение клиенту, само не включается.
        for kind in set(HandlingRuleKind.values) - {RETURN}:
            with self.subTest(kind=kind):
                self.assertEqual(
                    (rules[kind].enabled, rules[kind].delay_minutes, rules[kind].recipients),
                    (False, None, []),
                )
        changed = self.change({"enabled": False})
        self.assertEqual((changed.enabled, changed.version), (False, 2))
        self.assertEqual(changed.updated_by_id, self.owner.user_id)
        self.assertIsNotNone(changed.updated_at)
        self.assertEqual(
            set(HandlingRule.objects.exclude(kind=RETURN).values_list("enabled", "version")),
            {(False, 1)},
        )

    def test_saving_the_same_settings_keeps_the_version(self) -> None:
        rule = rule_for(self.organization.pk, RETURN)
        same = self.change({"enabled": True, "delay_minutes": rule.delay_minutes})
        self.assertEqual((same.version, same.updated_at), (1, None))

    def test_only_catalogued_conditions_recipients_and_delays_are_accepted(self) -> None:
        for changes in (
            {"conditions": {"sql": "1 = 1"}},
            {"conditions": {"python": "__import__('os')"}},
            {"conditions": ["group"]},
            {"recipients": ["EVERYONE"]},
            {"recipients": [RuleRecipient.CONVERSATION_GROUP] * 2},
            {"recipients": [{"user": self.owner.user_id}]},
            {"recipients": []},
            {"delay_minutes": 0},
            {"delay_minutes": 24 * 60 + 1},
            {"delay_minutes": "5"},
            {"delay_minutes": True},
            {"delay_minutes": None},
            {"enabled": "yes"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.change(changes)
        rule = rule_for(self.organization.pk, RETURN)
        self.assertEqual((rule.version, rule.conditions), (1, {}))

    def test_rule_without_an_implemented_action_cannot_be_enabled(self) -> None:
        for kind in set(HandlingRuleKind.values) - {RETURN}:
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                self.change({"enabled": True, "delay_minutes": 5}, kind=kind)
        self.assertFalse(HandlingRule.objects.exclude(kind=RETURN).filter(enabled=True).exists())

    def test_only_settings_managers_change_rules(self) -> None:
        operator = tenant_context_for(self.operator.user, self.organization)
        with self.assertRaises(PermissionDenied):
            self.change({"enabled": False}, context=operator)
        self.assertTrue(rule_for(self.organization.pk, RETURN).enabled)

    def test_queue_delay_and_rule_delay_are_one_number(self) -> None:
        self.assertEqual(rule_for(self.organization.pk, RETURN).delay_minutes, 10)
        client = TenantAPIClient()
        client.force_authenticate(self.owner.user)
        response = client.patch(
            "/api/v1/conversations/queue-policy/", {"assignment_timeout_minutes": 3}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        rule = rule_for(self.organization.pk, RETURN)
        self.assertEqual((rule.delay_minutes, rule.version), (3, 2))
        self.change({"delay_minutes": 20})
        self.assertEqual(policy_for(self.organization).assignment_timeout_minutes, 20)
        # Остальные пороги очереди правило не трогает.
        self.assertEqual(policy_for(self.organization).remind_after_minutes, 5)

    def test_database_keeps_one_rule_per_kind_and_one_record_per_logical_key(self) -> None:
        rule = rule_for(self.organization.pk, RETURN)
        with self.assertRaises(IntegrityError), transaction.atomic():
            HandlingRule.objects.create(organization=self.organization, kind=RETURN)
        with self.assertRaises(IntegrityError), transaction.atomic():
            HandlingRule.objects.filter(pk=rule.pk).update(delay_minutes=None)
        execution = self.assign(self.operator)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RuleExecution.objects.create(
                rule=rule, conversation=self.conversation, rule_version=rule.version,
                source_event=execution.source_event, action=RuleAction.RETURN_TO_QUEUE,
                scheduled_for=execution.scheduled_for,
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            RuleExecution.objects.filter(pk=execution.pk).update(status="SKIPPED")
