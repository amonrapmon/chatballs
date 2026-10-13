from uuid import uuid4

from django.utils.translation import override

from chatballs.conversations.models import ControlMode
from chatballs.conversations.participant_services import add_participant, remove_participant
from chatballs.conversations.participant_test_base import ParticipantTestBase
from chatballs.conversations.participant_views import LimitInput
from chatballs.conversations.transfer_models import ConversationTransfer, TransferReason
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import EmployeeRole
from chatballs.identity.work_status_services import change_work_status
from chatballs.tenancy.context import TenantContext
from chatballs.testing import TenantAPIClient


class ParticipantUIContractTests(ParticipantTestBase):
    def setUp(self):
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.members[0].user)
        self.base = f"/api/v1/conversations/{self.conversation.pk}/"

    def test_directory_identifies_memberships_and_history_keeps_named_actors(self):
        directory = self.client.get("/api/v1/conversations/directory/").json()["employees"]
        self.assertEqual({row["membershipId"] for row in directory}, {member.pk for member in self.members})
        self.assertEqual({row["id"] for row in directory}, {member.user_id for member in self.members})
        row, _ = add_participant(
            context=self.context, conversation_id=self.conversation.pk,
            membership_id=self.members[1].pk, reason="Internal consultation",
        )
        active = self.client.get(self.base + "participants/").json()
        self.assertEqual(active["additionalParticipantLimit"], 5)
        self.assertEqual(active["items"][0]["member"]["membershipId"], self.members[1].pk)
        remove_participant(
            context=self.context, conversation_id=self.conversation.pk,
            participant_id=row.pk, reason="Finished",
        )
        self.members[1].blocked_at = row.joined_at
        self.members[1].save(update_fields=["blocked_at"])
        history = self.client.get(self.base + "participants/history/").json()["items"]
        self.assertEqual(history[0]["member"]["name"], self.members[1].user.email)
        self.assertEqual(history[0]["joinedBy"]["membershipId"], self.members[0].pk)
        self.assertEqual(history[0]["leftBy"]["membershipId"], self.members[0].pk)
        self.assertEqual(history[0]["leaveReason"], "Finished")
        self.client.force_authenticate(self.foreign_member.user)
        self.assertEqual(self.client.get(self.base + "participants/history/").status_code, 404)

    def test_limit_read_update_range_and_saved_metadata_are_tenant_scoped(self):
        url = "/api/v1/conversations/participant-limit/"
        self.assertEqual(self.client.get(url).json()["additionalParticipantLimit"], 5)
        self.assertEqual(self.client.patch(url, {"additionalParticipantLimit": 1}, format="json").status_code, 403)
        self.members[0].role = EmployeeRole.ADMIN
        self.members[0].save(update_fields=["role"])
        for value in (0, 11, -1, 1.5, None, "invalid"):
            response = self.client.patch(url, {"additionalParticipantLimit": value}, format="json")
            self.assertEqual(response.status_code, 400, value)
            self.assertEqual(response.json()["detail"], "Укажите число от 1 до 10")
        for value in (1, 10):
            response = self.client.patch(url, {"additionalParticipantLimit": value}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["additionalParticipantLimit"], value)
            self.assertEqual(response.json()["updatedBy"], self.members[0].user.email)
            self.assertTrue(response.json()["updatedAt"])
        self.assertEqual(self.client.get(url).json(), response.json())
        self.client.force_authenticate(self.foreign_member.user)
        foreign = self.client.get(url).json()
        self.assertEqual(foreign["additionalParticipantLimit"], 5)
        self.assertIsNone(foreign["updatedAt"])
        self.assertEqual(foreign["updatedBy"], "")

    def test_limit_errors_use_the_reader_language_at_request_time(self):
        for language, expected in (("en", "Enter a number from 1 to 10"), ("ru", "Укажите число от 1 до 10")):
            with override(language):
                serializer = LimitInput(data={"additionalParticipantLimit": 11})
                self.assertFalse(serializer.is_valid())
                self.assertEqual(list(serializer.errors["additionalParticipantLimit"]), [expected])

    def test_named_status_roster_and_journal_pagination_recheck_participation(self):
        group = EmployeeGroup.objects.create(organization=self.organization, name="Restricted")
        self.conversation.group = group
        self.conversation.control_mode = ControlMode.HUMAN
        self.conversation.save(update_fields=["group", "control_mode"])
        change_work_status(
            context=TenantContext.for_membership(self.members[1]), status="BREAK",
            expected_version=0, operation_id=uuid4(),
        )
        row, _ = add_participant(
            context=self.context, conversation_id=self.conversation.pk,
            membership_id=self.members[1].pk, reason="Internal bank check",
        )
        self.client.force_authenticate(self.members[1].user)
        roster = self.client.get(self.base + "participants/").json()
        self.assertEqual(roster["items"][0]["workStatus"]["status"], "BREAK")
        self.assertIn("online", roster["items"][0])
        access = self.client.get(self.base).json()["conversation"]["access"]
        self.assertTrue(access["isParticipant"])
        self.assertTrue(access["canReply"])
        self.assertFalse(access["canControl"])
        self.assertNotIn("conversations.participants", access["actions"])
        journal_url = self.base + "participation-journal/"
        journal = self.client.get(journal_url).json()
        self.assertEqual(journal["items"][0]["kind"], "JOINED")
        self.assertEqual(journal["items"][0]["reason"], "Internal bank check")
        inbox = self.client.get("/api/v1/conversations/").json()["items"]
        self.assertTrue(next(item for item in inbox if item["id"] == self.conversation.pk)["isParticipant"])
        remove_participant(
            context=self.context, conversation_id=self.conversation.pk,
            participant_id=row.pk, reason="Internal consultation complete",
        )
        self.assertEqual(self.client.get(journal_url).status_code, 404)
        lost = self.client.get(self.base)
        self.assertEqual(lost.status_code, 404)
        self.assertEqual(lost.json()["participationEndedBy"], self.members[0].user.email)
        self.assertNotIn("Internal consultation complete", str(lost.json()))
        self.client.force_authenticate(self.members[0].user)
        first = self.client.get(journal_url + "?kind=participants&pageSize=1").json()
        second = self.client.get(journal_url + "?kind=participants&pageSize=1&page=2").json()
        self.assertEqual(first["total"], 2)
        self.assertEqual(first["pageCount"], 2)
        self.assertEqual(first["items"][0]["kind"], "LEFT")
        self.assertEqual(second["items"][0]["kind"], "JOINED")
        self.assertEqual(self.client.get(journal_url + "?kind=transfers").json()["total"], 0)
        reason = TransferReason.objects.create(
            organization=self.organization, code="consultation", name="Renamed", is_active=False,
        )
        ConversationTransfer.objects.create(
            organization=self.organization, conversation=self.conversation, reason=reason,
            initiated_by=self.members[0].user, new_operator=self.members[0].user,
            operation_id=uuid4(), reason_code=reason.code, reason_name="Original", comment="Private note",
        )
        mixed = self.client.get(journal_url).json()
        self.assertEqual(mixed["total"], 3)
        transfer = self.client.get(journal_url + "?kind=transfers").json()["items"][0]
        self.assertEqual(transfer["comment"], "Private note")
        self.assertEqual(transfer["reason"], "Original")
        self.assertTrue(transfer["reasonChanged"])
        self.assertTrue(transfer["reasonInactive"])
        self.client.force_authenticate(self.foreign_member.user)
        self.assertEqual(self.client.get(journal_url).status_code, 404)
        self.assertNotIn("participationEndedBy", self.client.get(self.base).json())
