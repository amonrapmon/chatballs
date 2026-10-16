"""Tenant-защита правил и журнала: модель, ограничения БД и RLS под ролью app."""

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.models import Contact, Conversation
from chatballs.conversations.rules.models import HandlingRule, HandlingRuleKind, RuleExecution
from chatballs.conversations.rules.rule_test_base import RuleScene
from chatballs.conversations.rules.settings import rule_for
from chatballs.identity.models import HumanUser, Organization, OrganizationMembership
from chatballs.tenancy.database import tenant_atomic

RETURN = HandlingRuleKind.ASSIGNMENT_RETURN


class RuleGuardTests(RuleScene, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.foreign = Organization.objects.create(name="Foreign", slug="foreign-rules")
        self.foreign_user = HumanUser.objects.create_user(email="owner@foreign-rules.test")
        OrganizationMembership.objects.create(
            organization=self.foreign, user=self.foreign_user, role="OWNER"
        )
        channel = Channel.objects.create(organization=self.foreign, code="foreign", name="Foreign")
        self.foreign_conversation = Conversation.objects.create(
            organization=self.foreign, channel=channel,
            contact=Contact.objects.create(organization=self.foreign, name="Customer"),
        )
        self.foreign_rule = rule_for(self.foreign.pk, RETURN)
        self.execution = self.assign(self.operator)

    @staticmethod
    def app_role() -> None:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE chatballs_runtime_app")

    def copy(self, **changes) -> RuleExecution:
        fields = ("organization_id", "rule_id", "conversation_id", "source_event_id",
                  "rule_version", "scheduled_for")
        values = {field: getattr(self.execution, field) for field in fields}
        return RuleExecution(action="RETURN_TO_QUEUE", **{**values, **changes})

    def test_model_and_database_reject_foreign_relations(self) -> None:
        for changes in (
            {"organization_id": self.foreign.pk},
            {"rule_id": self.foreign_rule.pk},
            {"conversation_id": self.foreign_conversation.pk},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError):
                    self.copy(**changes).save()
                with self.assertRaises(DatabaseError), transaction.atomic():
                    RuleExecution.objects.filter(pk=self.execution.pk).update(**changes)
        with self.assertRaises(DatabaseError), transaction.atomic():
            HandlingRule.objects.filter(pk=self.execution.rule_id).update(
                updated_by_id=self.foreign_user.pk
            )

    def test_runtime_role_is_fail_closed_and_scoped_to_its_organization(self) -> None:
        with transaction.atomic():
            self.app_role()
            self.assertEqual(HandlingRule.objects.count(), 0)
            self.assertEqual(RuleExecution.objects.count(), 0)
            with self.assertRaises(DatabaseError), transaction.atomic():
                HandlingRule.objects.create(
                    organization=self.organization, kind=HandlingRuleKind.REPLY_REMINDER
                )
        with tenant_atomic(self.context):
            self.app_role()
            self.assertEqual(
                list(HandlingRule.objects.values_list("organization_id", flat=True)),
                [self.organization.pk],
            )
            self.assertEqual(
                list(RuleExecution.objects.values_list("pk", flat=True)), [self.execution.pk]
            )
            self.assertEqual(HandlingRule.objects.filter(pk=self.foreign_rule.pk).update(enabled=False), 0)
            with self.assertRaises(DatabaseError), transaction.atomic():
                HandlingRule.objects.create(
                    organization=self.foreign, kind=HandlingRuleKind.REPLY_REMINDER
                )
            # Журнал уходит вместе с диалогом: удалённый диалог не оставляет строк.
            self.conversation.delete()
            self.assertEqual(RuleExecution.objects.count(), 0)
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE NONE")
        self.assertTrue(HandlingRule.objects.get(pk=self.foreign_rule.pk).enabled)

    def test_tables_are_forced_rls_owned_by_schema_and_closed_to_platform(self) -> None:
        tables = [HandlingRule._meta.db_table, RuleExecution._meta.db_table]
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner) "
                "FROM pg_class WHERE relname = ANY(%s)", [tables],
            )
            self.assertEqual(cursor.fetchall(), [(True, True, "chatballs_schema")] * 2)
            for table in tables:
                cursor.execute(
                    "SELECT has_table_privilege('chatballs_runtime_platform', %s, 'SELECT')", [table]
                )
                self.assertFalse(cursor.fetchone()[0])
