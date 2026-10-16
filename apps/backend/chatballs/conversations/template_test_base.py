"""Shared setup for focused library acceptance tests on the Django test DB."""

from django.test import TestCase

from chatballs.identity.models import (
    EmployeeRole,
    HumanUser,
    Organization,
    OrganizationMembership,
)
from chatballs.testing import TenantAPIClient, tenant_context_for


class TemplateTestBase(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Library", slug="library")
        self.foreign = Organization.objects.create(name="Foreign", slug="foreign-library")
        self.owner = self.member("owner", EmployeeRole.OWNER)
        self.admin = self.member("admin", EmployeeRole.ADMIN)
        self.employee = self.member("employee")
        self.colleague = self.member("colleague")
        # A global user has independent membership ownership in the other tenant.
        self.foreign_member = OrganizationMembership.objects.create(
            organization=self.foreign, user=self.employee.user, role=EmployeeRole.EMPLOYEE,
        )
        self.context = tenant_context_for(self.employee.user, self.organization)
        self.client = self.client_for(self.employee)
        self.owner_client = self.client_for(self.owner)
        self.admin_client = self.client_for(self.admin)
        self.colleague_client = self.client_for(self.colleague)
        self.base = f"/api/v1/organizations/{self.organization.public_id}/conversations/templates/"

    def member(self, name, role=EmployeeRole.EMPLOYEE):
        user = HumanUser.objects.create_user(email=f"{name}@library.test")
        return OrganizationMembership.objects.create(organization=self.organization, user=user, role=role)

    @staticmethod
    def client_for(membership):
        client = TenantAPIClient()
        client.force_authenticate(membership.user)
        client.organization_public_id = membership.organization.public_id
        return client

    def create(self, client=None, resource="", scope="PERSONAL", **data):
        payload = {"scope": scope, **data}
        if not resource:
            payload = {"title": "Greeting", "text": "Hello {{client_name}}", **payload}
        else:
            payload = {"name": "Greeting", **payload}
        return (client or self.client).post(self.base + resource, payload, format="json")
