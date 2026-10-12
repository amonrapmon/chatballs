from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction

from chatballs.conversations.domain_event_models import (
    ConversationEvent,
    ConversationEventHistoryStart,
)
from chatballs.conversations.domain_event_test_base import DomainEventTestBase
from chatballs.tenancy.database import tenant_atomic


class DomainEventGuardTests(DomainEventTestBase):
    def test_model_and_database_reject_every_foreign_snapshot(self):
        for changes in (
            {"organization_id": self.foreign.pk},
            {"conversation_id": self.foreign_conversation.pk},
            {"initiated_by_id": self.foreign_user.pk},
            {"responsible_id": self.foreign_user.pk},
            {"group_id": self.foreign_group.pk},
            {"connection_id": self.foreign_connection.pk},
            {"transport": "EMAIL"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError):
                    self.row(**changes).save()
                with self.assertRaises(DatabaseError), transaction.atomic():
                    ConversationEvent.objects.bulk_create([self.row(**changes)])

    @staticmethod
    def app_role():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE chatballs_runtime_app")

    def test_runtime_role_is_fail_closed_and_cannot_read_write_other_tenants(self):
        row = self.row()
        row.save()
        foreign = self.row(
            organization_id=self.foreign.pk, conversation_id=self.foreign_conversation.pk,
            actor_kind="SYSTEM", initiated_by_id=None, responsible_id=None, group_id=None,
            connection_id=None, transport=None,
        )
        foreign.save()
        with transaction.atomic():
            self.app_role()
            self.assertEqual(ConversationEvent.objects.count(), 0)
            with self.assertRaises(DatabaseError), transaction.atomic():
                ConversationEvent.objects.bulk_create([self.row()])
        with tenant_atomic(self.context):
            self.app_role()
            self.assertEqual(list(ConversationEvent.objects.values_list("pk", flat=True)), [row.pk])
            valid = self.row(event_type="PUBLIC_REPLY")
            ConversationEvent.objects.bulk_create([valid])
            self.assertEqual(valid.sequence, 2)
            for changes in ({"organization_id": self.foreign.pk},
                            {"conversation_id": self.foreign_conversation.pk},
                            {"responsible_id": self.foreign_user.pk}):
                with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                    ConversationEvent.objects.bulk_create([self.row(**changes)])
            with self.assertRaises(DatabaseError), transaction.atomic():
                ConversationEvent.objects.filter(pk=row.pk).update(event_type="CLOSED")
            self.assertEqual(ConversationEvent.objects.filter(
                conversation_id=self.foreign_conversation.pk
            ).delete()[0], 0)
            # Check this journal's DELETE grant independently of other histories:
            # comments from main intentionally do not grant DELETE to app.
            ConversationEvent.objects.filter(conversation_id=self.conversation.pk).delete()
            self.assertEqual(ConversationEvent.objects.count(), 0)
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE NONE")
        self.assertTrue(ConversationEvent.objects.filter(pk=foreign.pk).exists())

    def test_rls_configuration_and_boundary_read_only_for_app(self):
        # TransactionTestCase flushes migration data between tests on reuse.
        ConversationEventHistoryStart.objects.get_or_create(pk=1)
        tables = [ConversationEvent._meta.db_table, ConversationEventHistoryStart._meta.db_table]
        with connection.cursor() as cursor:
            cursor.execute("SELECT relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner) "
                           "FROM pg_class WHERE relname = ANY(%s)", [tables])
            self.assertEqual(cursor.fetchall(), [(True, True, "chatballs_schema")] * 2)
            for table in tables:
                cursor.execute("SELECT has_table_privilege('chatballs_runtime_platform', %s, 'SELECT')", [table])
                self.assertFalse(cursor.fetchone()[0])
        with transaction.atomic():
            self.app_role()
            with connection.cursor() as cursor:
                cursor.execute("SELECT available_from FROM conversations_conversationeventhistorystart WHERE id=1")
                self.assertIsNotNone(cursor.fetchone()[0])
            with self.assertRaises(DatabaseError), transaction.atomic():
                ConversationEventHistoryStart.objects.filter(pk=1).delete()
