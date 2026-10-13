from datetime import timedelta

from django.utils import timezone

from chatballs.conversations.models import ControlMode, Message, MessageAuthor, SystemEvent
from chatballs.conversations.participant_models import ConversationParticipant
from chatballs.conversations.services import claim_conversation
from chatballs.conversations.transfer_models import ConversationTransfer
from chatballs.conversations.transfer_services import record_transfer
from chatballs.conversations.transfer_test_base import TransferTestBase
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import EmployeeRole


class ActivityHistoryTests(TransferTestBase):
    def setUp(self):
        super().setUp()
        self.history_url = (
            f"/api/v1/organizations/{self.organization.public_id}/conversations/"
            f"{self.conversation.pk}/activity-history/"
        )

    def test_global_order_paging_filters_and_preserved_reason_snapshot(self):
        now = timezone.now()
        participant = ConversationParticipant.objects.create(
            organization=self.organization, conversation=self.conversation,
            membership=self.members[EmployeeRole.EMPLOYEE], joined_by=self.context.membership,
            join_reason="Consultation",
        )
        ConversationParticipant.objects.filter(pk=participant.pk).update(
            joined_at=now - timedelta(minutes=3), left_at=now - timedelta(minutes=1),
            left_by_id=self.context.membership.pk, leave_reason="Resolved",
        )
        transfer = record_transfer(
            context=self.context, conversation_id=self.conversation.pk,
            previous_operator_id=self.members[EmployeeRole.ADMIN].user_id,
            new_operator_id=self.members[EmployeeRole.EMPLOYEE].user_id,
            reason_id=self.reason.pk, comment="Private detail",
            operation_id="58f80f21-23cf-42b1-b5a9-90b5a6775e5a",
        )
        ConversationTransfer.objects.filter(pk=transfer.pk).update(occurred_at=now - timedelta(minutes=2))
        self.reason.name = "New name"
        self.reason.is_active = False
        self.reason.save(update_fields=["name", "is_active"])
        Message.objects.create(
            organization=self.organization, conversation=self.conversation,
            author_type=MessageAuthor.SYSTEM, system_event=SystemEvent.OPERATOR_TOOK,
            system_params={"operator": "Owner", "fromQueue": True},
        )
        # Legacy events cannot establish that the operation came from a queue.
        Message.objects.create(
            organization=self.organization, conversation=self.conversation,
            author_type=MessageAuthor.SYSTEM, system_event=SystemEvent.OPERATOR_TOOK,
            system_params={"operator": "Legacy"},
        )
        first = self.client.get(self.history_url, {"pageSize": 2})
        second = self.client.get(self.history_url, {"pageSize": 2, "page": 2})
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data["total"], 4)
        self.assertEqual(first.data["pageCount"], 2)
        rows = first.data["items"] + second.data["items"]
        self.assertEqual([row["kind"] for row in rows], ["CLAIM", "LEAVE", "TRANSFER", "JOIN"])
        self.assertEqual(len({row["id"] for row in rows}), 4)
        self.assertEqual(rows[1]["reason"]["name"], "Resolved")
        self.assertEqual(rows[3]["reason"]["name"], "Consultation")
        self.assertEqual(rows[3]["recipient"]["id"], self.members[EmployeeRole.EMPLOYEE].user_id)
        self.assertEqual(rows[2]["reason"]["name"], "Specialist needed")
        self.assertEqual(rows[2]["reason"]["currentName"], "New name")
        self.assertFalse(rows[2]["reason"]["isActive"])
        self.assertEqual(rows[2]["comment"], "Private detail")
        for kind, expected in (("participants", ["LEAVE", "JOIN"]), ("transfers", ["TRANSFER"])):
            filtered = self.client.get(self.history_url, {"kind": kind})
            self.assertEqual([row["kind"] for row in filtered.data["items"]], expected)

    def test_foreign_and_lost_access_do_not_expose_journal(self):
        foreign_url = self.history_url.replace(f"/{self.conversation.pk}/", f"/{self.foreign_conversation.pk}/")
        self.assertEqual(self.client.get(foreign_url).status_code, 404)
        group = EmployeeGroup.objects.create(organization=self.organization, name="Private")
        self.conversation.group = group
        self.conversation.save(update_fields=["group"])
        self.client.force_authenticate(self.members[EmployeeRole.EMPLOYEE].user)
        self.assertEqual(self.client.get(self.history_url).status_code, 404)

    def test_empty_bounded_pages_and_invalid_filter(self):
        empty = self.client.get(self.history_url, {"kind": "participants", "pageSize": 1000})
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.data["items"], [])
        self.assertEqual(empty.data["pageSize"], 100)
        self.assertEqual(self.client.get(self.history_url, {"kind": "unknown"}).status_code, 400)

    def test_real_claim_records_queue_origin_and_actor_without_backfill(self):
        self.conversation.assigned_operator = None
        self.conversation.control_mode = ControlMode.PAUSED
        self.conversation.waiting_since = timezone.now()
        self.conversation.save(update_fields=["assigned_operator", "control_mode", "waiting_since"])
        claim_conversation(context=self.context, conversation_id=self.conversation.pk)
        claimed = self.client.get(self.history_url).data["items"]
        self.assertEqual(len(claimed), 1)
        self.assertEqual(claimed[0]["actor"]["id"], self.context.actor_user.pk)
        self.conversation.refresh_from_db()
        self.conversation.control_mode = ControlMode.AI
        self.conversation.save(update_fields=["control_mode"])
        claim_conversation(context=self.context, conversation_id=self.conversation.pk)
        self.assertEqual(self.client.get(self.history_url).data["total"], 1)
