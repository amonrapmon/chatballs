"""Current team filter identities and audited revocation on real test PostgreSQL."""

from django.utils import timezone

from chatballs.conversations import test_team_result_scope as setup
from chatballs.conversations.support_report_test_base import SupportReportTestBase
from chatballs.identity.models import AuditEvent, AuditResult, OrganizationMembership
from chatballs.identity.policy import get_effective_access


class ReportDirectoryTests(SupportReportTestBase):
    def setUp(self):
        setup.TeamResultScopeTests.setUp(self)
        self.url = self.root + "support-report/access/"

    def test_current_team_directory_contains_no_administrative_fields_or_foreign_ids(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        data = response.data
        self.assertEqual(data["actions"], ["reports.view", "reports.export"])
        self.assertEqual([row["id"] for row in data["groups"]], [self.group.pk])
        self.assertEqual([row["id"] for row in data["employees"]], [self.user.pk])
        self.assertEqual([row["id"] for row in data["connections"]], [self.connection.pk])
        self.assertNotIn("totpEnabled", data["employees"][0])
        self.assertNotIn("permissions", data["employees"][0])
        self.assertNotIn("phone", data["employees"][0])
        self.assertEqual(get_effective_access(self.supervisor)["reportCapabilities"], data["actions"])
        self.assertTrue(data["restricted"])
        self.assertIn(data["timezone"], data["timezones"])

    def test_revocation_clears_directory_and_reads_only_own_tenant_audit(self):
        self.link.delete()
        own = AuditEvent.objects.create(
            organization=self.organization, actor=self.user, object_type="HumanUser",
            object_id=str(self.supervisor.user_id), result=AuditResult.SUCCESS,
            action="identity.employee_supervised_groups_changed",
            payload={"oldGroupIds": [self.group.pk], "groupIds": []},
        )
        AuditEvent.objects.create(
            organization=self.organization, actor=self.user, object_type="HumanUser",
            object_id=str(self.outsider.user_id), result=AuditResult.SUCCESS,
            action=own.action, payload=own.payload,
        )
        AuditEvent.objects.create(
            organization=self.foreign, actor=self.foreign_user, object_type="HumanUser",
            object_id=str(self.supervisor.user_id), result=AuditResult.SUCCESS,
            action=own.action, payload=own.payload,
        )
        data = self.client.get(self.url).data
        self.assertEqual(data["revokedAt"], own.created_at.isoformat())
        for key in ("actions", "groups", "employees", "connections"):
            self.assertEqual(data[key], [])
        self.assertEqual(get_effective_access(self.supervisor)["reportCapabilities"], [])

    def test_empty_area_has_no_fabricated_revocation_and_role_loss_has_no_directory(self):
        self.link.delete()
        self.assertIsNone(self.client.get(self.url).data["revokedAt"])
        OrganizationMembership.objects.filter(pk=self.supervisor.pk).update(role="EMPLOYEE")
        data = self.client.get(self.url).data
        self.assertEqual(data["actions"], [])
        self.assertEqual(data["employees"], [])
        OrganizationMembership.objects.filter(pk=self.supervisor.pk).update(blocked_at=timezone.now())
        self.assertIn(self.client.get(self.url).status_code, (403, 404))

    def test_manager_directory_preserves_org_access_without_security_details(self):
        self.client.force_authenticate(self.user)
        data = self.client.get(self.url).data
        self.assertFalse(data["restricted"])
        self.assertEqual({row["id"] for row in data["groups"]}, {self.group.pk, self.other_group.pk})
        self.assertNotIn(self.foreign_user.pk, [row["id"] for row in data["employees"]])

    def test_waiting_replies_never_use_independent_ordinary_work_visibility(self):
        self.outside.assigned_operator = self.user
        self.outside.save(update_fields=["assigned_operator"])
        data = self.client.get(self.root + "support-report/", self.params).data
        self.assertEqual(data["employees"][0]["waitingReplies"], 1)
        self.link.delete()
        self.assertEqual(self.client.get(self.root + "support-report/", self.params).data["employees"], [])

    def test_foreign_tenant_and_anonymous_directory_are_denied(self):
        foreign = self.url.replace(str(self.organization.public_id), str(self.foreign.public_id))
        self.assertIn(self.client.get(foreign).status_code, (403, 404))
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url).status_code, (401, 403, 404))
