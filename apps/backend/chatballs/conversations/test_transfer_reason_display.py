from chatballs.conversations.transfer_services import record_transfer
from chatballs.conversations.transfer_test_base import TransferTestBase
from chatballs.identity.models import EmployeeRole


class TransferReasonDisplayTests(TransferTestBase):
    def test_name_only_creation_duplicate_validation_and_tenant_isolation(self):
        created = self.client.post(self.url, {"name": "New reason"}, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        reason = created.data["reason"]
        self.assertTrue(reason["code"])
        self.assertEqual(reason["usageCount"], 0)
        self.assertIsNone(reason["renamedAt"])
        duplicate = self.client.post(self.url, {"name": "  new REASON  "}, format="json")
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("названием", duplicate.data["detail"])
        other_tenant_name = self.client.post(self.url, {"name": self.foreign_reason.name}, format="json")
        self.assertEqual(other_tenant_name.status_code, 201)
        collision = self.client.patch(
            f"{self.url}{reason['id']}/", {"name": self.reason.name}, format="json",
        )
        self.assertEqual(collision.status_code, 400)
        unchanged = self.client.patch(
            f"{self.url}{reason['id']}/", {"name": reason["name"]}, format="json",
        )
        self.assertEqual(unchanged.status_code, 200)
        self.assertIsNone(unchanged.data["reason"]["renamedAt"])

    def test_rename_usage_and_history_keep_original_snapshot(self):
        row = record_transfer(
            context=self.context, conversation_id=self.conversation.pk,
            previous_operator_id=self.members[EmployeeRole.ADMIN].user_id,
            new_operator_id=self.members[EmployeeRole.EMPLOYEE].user_id,
            reason_id=self.reason.pk, comment="Internal", operation_id="aad4f3a8-0495-4731-b5fb-cae1b7d4b13d",
        )
        updated = self.client.patch(
            f"{self.url}{self.reason.pk}/", {"name": "Renamed"}, format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.data)
        reason = updated.data["reason"]
        self.assertEqual(reason["usageCount"], 1)
        self.assertEqual(reason["previousName"], "Specialist needed")
        self.assertIsNotNone(reason["renamedAt"])
        self.client.delete(f"{self.url}{self.reason.pk}/")
        history_url = f"/api/v1/organizations/{self.organization.public_id}/conversations/{self.conversation.pk}/transfers/"
        history = self.client.get(history_url)
        self.assertEqual(history.status_code, 200)
        item = history.data["items"][0]
        self.assertEqual(item["id"], row.pk)
        self.assertEqual(item["reason"]["name"], "Specialist needed")
        self.assertEqual(item["reason"]["currentName"], "Renamed")
        self.assertFalse(item["reason"]["isActive"])
        self.assertEqual(item["initiatedBy"]["id"], self.context.actor_user.pk)
        self.assertEqual(item["newOperator"]["id"], self.members[EmployeeRole.EMPLOYEE].user_id)
        foreign_url = history_url.replace(str(self.conversation.pk) + "/transfers", str(self.foreign_conversation.pk) + "/transfers")
        self.assertEqual(self.client.get(foreign_url).status_code, 404)
