"""Список сотрудников: рабочий статус, фильтр по нему и присутствие своей организации."""

from chatballs import presence
from chatballs.identity.models import EmployeeRole
from chatballs.identity.work_status_codes import WorkStatus
from chatballs.identity.work_status_testing import WorkStatusTestBase
from chatballs.testing import TenantAPIClient


class EmployeeAvailabilityTests(WorkStatusTestBase):
    def setUp(self):
        super().setUp()
        self.membership.role = EmployeeRole.ADMIN
        self.membership.save(update_fields=["role"])
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.user)
        self.url = f"/api/v1/organizations/{self.organization.public_id}/employees/"

    def test_saved_status_and_presence_are_separate(self):
        operation = self.change(WorkStatus.BREAK)
        presence.touch(self.organization.pk, self.user.pk)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        row = response.json()["items"][0]
        self.assertEqual(row["workStatus"], {
            "status": "BREAK", "version": 1, "changedAt": operation.changed_at.isoformat(),
        })
        self.assertTrue(row["online"])
        self.assertIsNotNone(row["lastSeenAt"])
        self.other.refresh_from_db()
        self.assertEqual(self.other.work_status, WorkStatus.UNAVAILABLE)
        self.assertIsNone(self.other.work_status_changed_at)

    def test_filter_uses_organization_membership_and_preserves_presence(self):
        self.change(WorkStatus.READY)
        presence.touch(self.foreign.pk, self.user.pk)
        page = self.client.get(self.url, {"workStatus": "READY", "pageSize": 1}).json()
        self.assertEqual(page["total"], 1)
        self.assertFalse(page["items"][0]["online"])
        self.assertIsNone(page["items"][0]["lastSeenAt"])
        self.assertEqual(self.client.get(self.url, {"workStatus": "UNAVAILABLE"}).json()["total"], 0)

    def test_initial_status_has_no_invented_timestamp(self):
        row = self.client.get(self.url).json()["items"][0]
        self.assertEqual(row["workStatus"], {"status": "UNAVAILABLE", "version": 0, "changedAt": None})

    def test_invalid_status_filter_is_rejected(self):
        self.assertEqual(self.client.get(self.url, {"workStatus": "ONLINE"}).status_code, 400)
