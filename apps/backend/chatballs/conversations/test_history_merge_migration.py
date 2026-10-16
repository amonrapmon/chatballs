"""Upgrade either accepted schema without losing its stored history."""

from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class HistoryMergeMigrationTests(TransactionTestCase):
    def upgrade(self, branch, history_model, history_fields, new_history_model):
        branch_schema = "internal_comments" if branch == "comment" else "participant_data"
        before = [
            ("tenancy", f"0042_{branch}_guards"),
            ("conversations", f"0031_{branch_schema}"),
        ]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        try:
            # Roll back both sibling branches first: targeting one guard alone
            # can leave its sibling's already-applied tables in the database.
            executor.migrate([
                ("tenancy", "0041_transfer_guards"),
                ("conversations", "0030_transfer_data"),
                ("identity", "0041_instance_tools_private_network"),
            ])
            executor = MigrationExecutor(connection)
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            organization = old.get_model("identity", "Organization").objects.create(
                name="Accepted history", slug="accepted-history",
            )
            author = old.get_model("identity", "HumanUser").objects.create(
                email="accepted@history.test",
            )
            member = old.get_model("identity", "OrganizationMembership").objects.create(
                organization_id=organization.pk, user_id=author.pk, role="OWNER",
            )
            channel = old.get_model("channels", "Channel").objects.create(
                organization_id=organization.pk, code="accepted", name="Accepted",
            )
            contact = old.get_model("conversations", "Contact").objects.create(
                organization_id=organization.pk, name="Customer",
            )
            conversation = old.get_model("conversations", "Conversation").objects.create(
                organization_id=organization.pk, channel_id=channel.pk, contact_id=contact.pk,
                assigned_operator_id=author.pk, assigned_at=timezone.now(), control_mode="HUMAN",
                note="Separate note", note_author_id=author.pk, note_updated_at=timezone.now(),
            )
            old.get_model("conversations", "Message").objects.create(
                organization_id=organization.pk, conversation_id=conversation.pk,
                author_type="CONTACT", text="Customer message",
            )
            reason = old.get_model("conversations", "TransferReason").objects.create(
                organization_id=organization.pk, code="specialist", name="Specialist",
            )
            old.get_model("conversations", "ConversationTransfer").objects.create(
                organization_id=organization.pk, conversation_id=conversation.pk,
                reason_id=reason.pk, previous_operator_id=None, new_operator_id=author.pk,
                initiated_by_id=author.pk, operation_id=uuid4(), reason_code=reason.code,
                reason_name=reason.name, comment="Internal transfer reason",
            )
            old.get_model("conversations", history_model).objects.create(
                organization_id=organization.pk, conversation_id=conversation.pk,
                **history_fields(author.pk, member.pk),
            )
            names = ("Conversation", "Message", "TransferReason", "ConversationTransfer", history_model)
            snapshots = {
                name: list(old.get_model("conversations", name).objects.order_by("pk").values())
                for name in names
            }
            MigrationExecutor(connection).migrate(latest)
            new = MigrationExecutor(connection).loader.project_state(latest).apps
            for name, snapshot in snapshots.items():
                self.assertEqual(
                    list(new.get_model("conversations", name).objects.order_by("pk").values()),
                    snapshot, name,
                )
            self.assertEqual(new.get_model("conversations", new_history_model).objects.count(), 0)
            self.assertEqual(new.get_model("identity", "Organization").objects.get(
                pk=organization.pk,
            ).additional_participant_limit, 5)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT relname, relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname = ANY(%s)",
                    [["conversations_conversationcomment", "conversations_conversationparticipant"]],
                )
                rows = cursor.fetchall()
                self.assertEqual(len(rows), 2)
                self.assertTrue(all(enabled and forced for _, enabled, forced in rows))
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_participant_branch_keeps_participants_transfers_and_assignment(self):
        self.upgrade(
            "participant", "ConversationParticipant",
            lambda author, member: {
                "membership_id": member, "joined_by_id": member, "join_reason": "Consultation",
            },
            "ConversationComment",
        )

    def test_comment_branch_keeps_comments_transfers_and_separate_note(self):
        self.upgrade(
            "comment", "ConversationComment",
            lambda author, member: {
                "author_id": author, "audience": "INTERNAL", "text": "Accepted comment",
                "operation_id": uuid4(),
            },
            "ConversationParticipant",
        )
