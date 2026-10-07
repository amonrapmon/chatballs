from datetime import timedelta

from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from chatballs.conversations.participant_models import ConversationParticipant
from chatballs.conversations.participant_test_base import ParticipantTestBase
from chatballs.identity.models import Organization
from chatballs.tenancy.database import tenant_atomic


class ParticipantGuardTests(ParticipantTestBase):
    @staticmethod
    def app_role():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE chatballs_runtime_app")

    def test_database_rejects_foreign_relations_on_bulk_insert_and_update(self):
        row = self.row()
        row.save()
        for changes in (
            {"organization_id": self.foreign.pk},
            {"conversation_id": self.foreign_conversation.pk},
            {"membership_id": self.foreign_member.pk},
            {"joined_by_id": self.foreign_member.pk},
            {"left_by_id": self.foreign_member.pk,
             "left_at": timezone.now() + timedelta(seconds=1), "leave_reason": "Completed"},
        ):
            with self.subTest(changes=changes):
                # Use another local member so uniqueness cannot mask a tenant error.
                with self.assertRaisesMessage(DatabaseError, "cross-tenant relation"), transaction.atomic():
                    ConversationParticipant.objects.bulk_create([
                        self.row(**{"membership_id": self.members[2].pk, **changes}),
                    ])
                with self.assertRaisesMessage(DatabaseError, "cross-tenant relation"), transaction.atomic():
                    ConversationParticipant.objects.filter(pk=row.pk).update(**changes)

    def test_rls_requires_context_and_scopes_participation_and_limit(self):
        row = self.row()
        row.save()
        foreign_row = self.row(
            organization=self.foreign, conversation=self.foreign_conversation,
            membership=self.foreign_member, joined_by=self.foreign_member,
        )
        foreign_row.save()
        with transaction.atomic():
            self.app_role()
            self.assertEqual(ConversationParticipant.objects.count(), 0)
            self.assertEqual(Organization.objects.count(), 0)
            with self.assertRaises(DatabaseError), transaction.atomic():
                ConversationParticipant.objects.bulk_create([self.row(membership=self.members[2])])
        with tenant_atomic(self.context):
            self.app_role()
            self.assertEqual(list(ConversationParticipant.objects.values_list("pk", flat=True)), [row.pk])
            self.assertEqual(ConversationParticipant.objects.filter(pk=foreign_row.pk).update(join_reason="Changed"), 0)
            self.assertEqual(Organization.objects.filter(pk=self.foreign.pk).update(additional_participant_limit=0), 0)
            self.assertEqual(Organization.objects.get(pk=self.organization.pk).additional_participant_limit, 5)
            self.assertEqual(Organization.objects.filter(pk=self.organization.pk).update(additional_participant_limit=2), 1)
            # Runtime role can insert and end participation within its own tenant.
            local = self.row(membership=self.members[2])
            local.save()
            local.left_at = timezone.now()
            local.left_by = self.members[0]
            local.leave_reason = "Completed"
            local.save()
            with self.assertRaises(DatabaseError), transaction.atomic():
                ConversationParticipant.objects.bulk_create([self.row(
                    organization=self.foreign, conversation=self.foreign_conversation,
                    membership=self.foreign_member, joined_by=self.foreign_member,
                    left_at=timezone.now() + timedelta(seconds=1),
                    left_by=self.foreign_member, leave_reason="Completed",
                )])

    def test_guard_configuration_forces_rls_and_grants_no_platform_access(self):
        table = ConversationParticipant._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner) "
                "FROM pg_class WHERE relname = %s", [table],
            )
            self.assertEqual(cursor.fetchone(), (True, True, "chatballs_schema"))
            cursor.execute("SELECT has_table_privilege('chatballs_runtime_platform', %s, 'SELECT')", [table])
            self.assertFalse(cursor.fetchone()[0])
