from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction

from chatballs.conversations.transfer_models import ConversationTransfer, TransferReason
from chatballs.conversations.transfer_test_base import TransferTestBase
from chatballs.identity.models import EmployeeRole
from chatballs.tenancy.database import tenant_atomic


class TransferGuardTests(TransferTestBase):
    def row(self, **changes):
        return ConversationTransfer(**{
            "organization_id": self.organization.pk, "conversation_id": self.conversation.pk,
            "reason_id": self.reason.pk,
            "previous_operator_id": self.members[EmployeeRole.ADMIN].user_id,
            "new_operator_id": self.members[EmployeeRole.EMPLOYEE].user_id,
            "initiated_by_id": self.context.actor_user.pk,
            "operation_id": uuid4(), "reason_code": self.reason.code,
            "reason_name": self.reason.name, "comment": "Internal",
            **changes,
        })

    def test_model_rejects_cross_organization_relations_and_participants(self):
        for changes in (
            {"conversation_id": self.foreign_conversation.pk},
            {"organization_id": self.foreign.pk}, {"reason_id": self.foreign_reason.pk},
            {"previous_operator_id": self.foreign_user.pk},
            {"new_operator_id": self.foreign_user.pk},
            {"initiated_by_id": self.foreign_user.pk},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.row(**changes).save()

    def test_database_rejects_bulk_create_and_update_bypassing_model_validation(self):
        for changes in (
            {"conversation_id": self.foreign_conversation.pk},
            {"organization_id": self.foreign.pk}, {"reason_id": self.foreign_reason.pk},
            {"previous_operator_id": self.foreign_user.pk},
            {"new_operator_id": self.foreign_user.pk},
            {"initiated_by_id": self.foreign_user.pk},
        ):
            with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                ConversationTransfer.objects.bulk_create([self.row(**changes)])
        row = self.row()
        row.save()
        for changes in ({"reason_id": self.foreign_reason.pk}, {"organization_id": self.foreign.pk},
                        {"conversation_id": self.foreign_conversation.pk},
                        {"previous_operator_id": self.foreign_user.pk},
                        {"new_operator_id": self.foreign_user.pk},
                        {"initiated_by_id": self.foreign_user.pk}):
            with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                ConversationTransfer.objects.filter(pk=row.pk).update(**changes)

    @staticmethod
    def app_role():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE chatballs_runtime_app")

    def test_rls_fail_closed_and_tenant_read_write_isolation(self):
        row = self.row()
        row.save()
        with transaction.atomic():
            self.app_role()
            self.assertEqual(TransferReason.objects.count(), 0)
            self.assertEqual(ConversationTransfer.objects.count(), 0)
        with tenant_atomic(self.context):
            self.app_role()
            self.assertEqual(list(TransferReason.objects.values_list("pk", flat=True)), [self.reason.pk])
            self.assertEqual(list(ConversationTransfer.objects.values_list("pk", flat=True)), [row.pk])
            self.assertEqual(TransferReason.objects.filter(pk=self.foreign_reason.pk).update(name="Changed"), 0)
            for model, instance in (
                (TransferReason, TransferReason(organization=self.foreign, code="blocked", name="Blocked")),
                (ConversationTransfer, self.row(organization_id=self.foreign.pk)),
            ):
                with self.assertRaises(DatabaseError), transaction.atomic():
                    model.objects.bulk_create([instance])

    def test_guard_configuration_uses_forced_rls_and_no_platform_grants(self):
        tables = [TransferReason._meta.db_table, ConversationTransfer._meta.db_table]
        with connection.cursor() as cursor:
            cursor.execute("SELECT relname, relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner) "
                           "FROM pg_class WHERE relname = ANY(%s) ORDER BY relname", [tables])
            rows = cursor.fetchall()
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(enabled and forced and owner == "chatballs_schema" for _, enabled, forced, owner in rows))
            for table in tables:
                cursor.execute("SELECT has_table_privilege('chatballs_runtime_platform', %s, 'SELECT')", [table])
                self.assertFalse(cursor.fetchone()[0])
