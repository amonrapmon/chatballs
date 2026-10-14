"""Journal metadata uses the reader's tenant and never grants settings access."""

from django.test import TestCase

from chatballs.conversations.rules.rule_test_base import RuleScene
from chatballs.identity.models import EmployeeRole, HumanUser, Organization, OrganizationMembership
from chatballs.testing import TenantAPIClient

JOURNAL = "/api/v1/conversations/rule-executions/"


class RuleJournalTimezoneTests(RuleScene, TestCase):
    slug = "journal-timezone"

    def client_for(self, membership):
        client = TenantAPIClient()
        client.force_authenticate(membership.user)
        return client

    def test_timezone_is_tenant_metadata_without_granting_settings_access(self):
        admin = self.employee("admin", EmployeeRole.ADMIN)
        lead = self.supervisor("lead", self.group)
        execution = self.assign(self.operator)
        self.organization.timezone = "Asia/Tokyo"
        self.organization.save(update_fields=["timezone"])
        for reader in (admin, lead):
            with self.subTest(role=reader.role):
                response = self.client_for(reader).get(JOURNAL, {"timezone": "UTC"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["timezone"], "Asia/Tokyo")
                self.assertEqual([item["id"] for item in response.json()["items"]], [execution.pk])
        self.assertEqual(self.client_for(lead).get("/api/v1/conversations/rules/").status_code, 403)
        self.assertEqual(self.client_for(self.operator).get(JOURNAL).status_code, 403)
        self.assertEqual(self.client_for(self.supervisor("empty")).get(JOURNAL).status_code, 403)
        other = Organization.objects.create(name="Other timezone", slug="other-timezone", timezone="America/New_York")
        stranger = OrganizationMembership.objects.create(
            user=HumanUser.objects.create_user(email="owner@other-timezone.test"),
            organization=other, role=EmployeeRole.OWNER,
        )
        body = self.client_for(stranger).get(JOURNAL, {"conversationId": self.conversation.pk}).json()
        self.assertEqual((body["timezone"], body["items"]), ("America/New_York", []))
