"""Availability API follows the supervisor model merged from main."""

from django.utils import timezone

from chatballs.identity.group_models import EmployeeGroup, EmployeeGroupMember
from chatballs.identity.models import EmployeeRole, HumanUser, OrganizationMembership
from chatballs.identity.supervision_models import EmployeeGroupSupervision
from chatballs.identity.work_status_testing import WorkStatusTestBase
from chatballs.testing import TenantAPIClient


class WorkStatusSupervisorTests(WorkStatusTestBase):
    def setUp(self):
        super().setUp()
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.user)
        colleague = HumanUser.objects.create(email="colleague@status.test")
        self.colleague = OrganizationMembership.objects.create(
            organization=self.organization, user=colleague, role=EmployeeRole.EMPLOYEE,
        )
        self.base = f"/api/v1/organizations/{self.organization.public_id}/employees/"
        self.own_url = self.base + "me/work-status/"

    def test_reads_only_controlled_groups_and_revocation_is_immediate(self):
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(role=EmployeeRole.SUPERVISOR)
        controlled = EmployeeGroup.objects.create(organization=self.organization, name="Controlled")
        ordinary = EmployeeGroup.objects.create(organization=self.organization, name="Ordinary")
        foreign = EmployeeGroup.objects.create(organization=self.foreign, name="Foreign")
        EmployeeGroupMember.objects.create(group=ordinary, employee=self.membership)
        link = EmployeeGroupMember.objects.create(group=ordinary, employee=self.colleague)
        urls = [self.base + f"{self.colleague.user_id}/work-status/" + suffix for suffix in ("", "history/")]

        def denied():
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, 404)

        denied()  # Empty area and ordinary membership never grant team reads.
        supervision = EmployeeGroupSupervision.objects.create(group=controlled, employee=self.membership)
        denied()
        link.group = controlled
        link.save(update_fields=["group"])
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.get(self.base + "999999/work-status/").status_code, 404)
        self.assertEqual(self.client.get(self.own_url).status_code, 200)
        self.assertEqual(self.client.post(urls[0], {}, format="json").status_code, 405)
        supervision.delete()
        denied()
        EmployeeGroupMember.objects.create(group=foreign, employee=self.other)
        foreign_url = self.own_url.replace(str(self.organization.public_id), str(self.foreign.public_id))
        self.assertEqual(self.client.get(foreign_url).status_code, 200)
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(blocked_at=timezone.now())
        self.assertEqual(self.client.get(self.own_url).status_code, 404)
