"""Preserve either accepted branch when installing the combined tenant guards."""

from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class AssistanceHistoryMergeTests(TransactionTestCase):
    common = [
        ("tenancy", "0040_agent_tool_guards"),
        ("ai", "0024_agenttool"),
        ("conversations", "0029_tool_called_event"),
        ("identity", "0041_instance_tools_private_network"),
    ]

    def upgrade(self, assistance):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        leaves = executor.loader.graph.leaf_nodes("tenancy")
        self.assertEqual(len(leaves), 1)
        self.assertIn(("tenancy", "0044_merge_assistance_history"),
                      executor.loader.graph.forwards_plan(leaves[0]))
        try:
            executor.migrate(self.common)
            before = (
                [("tenancy", "0041_reply_assistance_guards")]
                if assistance else
                [("tenancy", "0043_merge_comments_participants"), ("ai", "0024_agenttool")]
            )
            executor = MigrationExecutor(connection)
            executor.migrate(before)
            old = executor.loader.project_state(before).apps
            org = old.get_model("identity", "Organization").objects.create(
                name="Accepted branch", slug="accepted-branch",
            )
            user = old.get_model("identity", "HumanUser").objects.create(
                email="accepted-branch@example.test",
            )
            member = old.get_model("identity", "OrganizationMembership").objects.create(
                organization_id=org.pk, user_id=user.pk, role="OWNER",
            )
            channel = old.get_model("channels", "Channel").objects.create(
                organization_id=org.pk, name="Accepted", code="accepted",
            )
            agent = old.get_model("ai", "AIAgent").objects.create(
                organization_id=org.pk, channel_id=channel.pk, name="Accepted",
                **({"assistance_enabled": True} if assistance else {}),
            )
            contact = old.get_model("conversations", "Contact").objects.create(
                organization_id=org.pk, name="Customer",
            )
            conversation = old.get_model("conversations", "Conversation").objects.create(
                organization_id=org.pk, channel_id=channel.pk, contact_id=contact.pk,
                control_mode="HUMAN", assigned_operator_id=user.pk, note="Separate note",
            )
            old.get_model("conversations", "Message").objects.create(
                organization_id=org.pk, conversation_id=conversation.pk,
                author_type="CONTACT", text="Customer question",
            )
            models = [("conversations", "Conversation"), ("conversations", "Message")]
            if assistance:
                attempt = old.get_model("ai", "ReplyAssistanceAttempt").objects.create(
                    organization_id=org.pk, conversation_id=conversation.pk, agent_id=agent.pk,
                    requested_by_id=member.pk, operation_key="initial", history_version="v1",
                )
                suggestion_model = old.get_model("ai", "ReplySuggestion")
                for position, text in ((1, "Original"), (2, "Alternative")):
                    suggestion = suggestion_model.objects.create(
                        organization_id=org.pk, attempt_id=attempt.pk, requested_by_id=member.pk,
                        position=position, operation_key=f"variant-{position}", history_version="v1",
                    )
                    suggestion_model.objects.filter(pk=suggestion.pk).update(
                        status="READY", started_at=timezone.now(), completed_at=timezone.now(),
                        original_text=text, rejected_by_id=member.pk, rejected_at=timezone.now(),
                    )
                models += [("ai", "ReplyAssistanceAttempt"), ("ai", "ReplySuggestion")]
            else:
                reason = old.get_model("conversations", "TransferReason").objects.create(
                    organization_id=org.pk, code="specialist", name="Specialist",
                )
                old.get_model("conversations", "ConversationTransfer").objects.create(
                    organization_id=org.pk, conversation_id=conversation.pk, reason_id=reason.pk,
                    new_operator_id=user.pk, initiated_by_id=user.pk, operation_id=uuid4(),
                    reason_code=reason.code, reason_name=reason.name, comment="Internal transfer",
                )
                old.get_model("conversations", "ConversationParticipant").objects.create(
                    organization_id=org.pk, conversation_id=conversation.pk,
                    membership_id=member.pk, joined_by_id=member.pk, join_reason="Consultation",
                )
                old.get_model("conversations", "ConversationComment").objects.create(
                    organization_id=org.pk, conversation_id=conversation.pk, author_id=user.pk,
                    text="Internal comment", audience="INTERNAL", operation_id=uuid4(),
                )
                models += [("conversations", name) for name in (
                    "TransferReason", "ConversationTransfer", "ConversationParticipant", "ConversationComment",
                )]
            snapshots = {
                key: list(old.get_model(*key).objects.order_by("pk").values()) for key in models
            }
            MigrationExecutor(connection).migrate(latest)
            new = MigrationExecutor(connection).loader.project_state(latest).apps
            for key, snapshot in snapshots.items():
                self.assertEqual(list(new.get_model(*key).objects.order_by("pk").values()), snapshot)
            self.assertEqual(new.get_model("ai", "AIAgent").objects.get(
                pk=agent.pk,
            ).assistance_enabled, assistance)
            self.assertEqual(new.get_model("identity", "Organization").objects.get(
                pk=org.pk,
            ).additional_participant_limit, 5)
            absent = (
                [("conversations", name) for name in (
                    "TransferReason", "ConversationTransfer", "ConversationParticipant", "ConversationComment",
                )] if assistance else
                [("ai", "ReplyAssistanceAttempt"), ("ai", "ReplySuggestion")]
            )
            for key in absent:
                self.assertEqual(new.get_model(*key).objects.count(), 0)
            tables = [
                "ai_replyassistanceattempt", "ai_replysuggestion", "ai_replysuggestionsend",
                "conversations_transferreason", "conversations_conversationtransfer",
                "conversations_conversationparticipant", "conversations_conversationcomment",
            ]
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = ANY(%s)",
                    [tables],
                )
                rows = cursor.fetchall()
                self.assertEqual(len(rows), len(tables))
                self.assertTrue(all(enabled and forced for enabled, forced in rows))
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_assistance_branch_keeps_variants_rejections_and_assignment(self):
        self.upgrade(assistance=True)

    def test_history_branch_keeps_transfers_participants_comments_and_assignment(self):
        self.upgrade(assistance=False)
