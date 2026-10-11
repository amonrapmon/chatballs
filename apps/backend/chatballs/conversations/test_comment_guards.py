from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction

from chatballs.conversations.comment_models import ConversationComment
from chatballs.conversations.comment_test_base import CommentTestBase
from chatballs.tenancy.database import tenant_atomic


class CommentGuardTests(CommentTestBase):
    @staticmethod
    def app_role():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE chatballs_runtime_app")

    def test_database_guards_cannot_be_bypassed_with_bulk_insert_or_update(self):
        changesets = (
            {"conversation_id": self.foreign_conversation.pk},
            {"organization_id": self.foreign.pk},
            {"author_id": self.foreign_author.pk},
            {"author_id": None}, {"audience": "PUBLIC"}, {"audience": ""},
            {"text": ""}, {"text": " \t\n"}, {"operation_id": None},
        )
        for changes in changesets:
            with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                ConversationComment.objects.bulk_create([self.row(**changes)])
        row = self.comment()
        for changes in changesets:
            with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                ConversationComment.objects.filter(pk=row.pk).update(**changes)

    def test_runtime_role_has_fail_closed_tenant_isolation_and_append_only_permissions(self):
        row = self.comment()
        foreign = self.comment(
            organization_id=self.foreign.pk, conversation_id=self.foreign_conversation.pk,
            author_id=self.foreign_author.pk,
        )
        with transaction.atomic():
            self.app_role()
            self.assertEqual(ConversationComment.objects.count(), 0)
            with self.assertRaises(DatabaseError), transaction.atomic():
                ConversationComment.objects.bulk_create([self.row()])
        with tenant_atomic(self.context):
            self.app_role()
            self.assertEqual(list(ConversationComment.objects.values_list("pk", flat=True)), [row.pk])
            self.assertFalse(ConversationComment.objects.filter(pk=foreign.pk).exists())
            own = self.comment()
            self.assertEqual(own.author_id, self.author.pk)
            with self.assertRaises(DatabaseError), transaction.atomic():
                ConversationComment.objects.bulk_create([self.row(
                    organization_id=self.foreign.pk, conversation_id=self.foreign_conversation.pk,
                    author_id=self.foreign_author.pk,
                )])
            # Even bypassing save() cannot rewrite or remove a sent record.
            with self.assertRaises(DatabaseError), transaction.atomic():
                ConversationComment.objects.filter(pk=row.pk).update(text="Changed")
            with self.assertRaises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute("DELETE FROM conversations_conversationcomment WHERE id = %s", [row.pk])
            row.refresh_from_db()
            self.assertEqual(row.text, "Internal discussion")
        self.assertEqual(ConversationComment.objects.count(), 0)

    def test_forced_rls_owner_and_platform_grants(self):
        table = ConversationComment._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner) "
                "FROM pg_class WHERE relname = %s", [table],
            )
            self.assertEqual(cursor.fetchone(), (True, True, "chatballs_schema"))
            cursor.execute("SELECT has_table_privilege('chatballs_runtime_platform', %s, 'SELECT')", [table])
            self.assertFalse(cursor.fetchone()[0])

    def test_model_derives_organization_and_rejects_wrong_author_before_insert(self):
        row = self.row(organization_id=None)
        row.save()
        self.assertEqual(row.organization_id, self.organization.pk)
        with self.assertRaises(ValidationError):
            self.row(author_id=self.foreign_author.pk).save()
