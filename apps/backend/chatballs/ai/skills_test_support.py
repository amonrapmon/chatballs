"""Test-database setup only; never seeds the running environment."""

import uuid

from chatballs.ai.models import AIAgent
from chatballs.channels.models import Channel
from chatballs.identity.models import (
    EmployeeRole,
    HumanUser,
    Organization,
    OrganizationMembership,
)
from chatballs.tenancy.context import TenantContext
from chatballs.testing import TenantAPIClient


class SkillsSetup:
    def setUp(self):
        super().setUp()
        self.organization = Organization.objects.create(name="Skills", slug="skills")
        self.other = Organization.objects.create(name="Other", slug="skills-other")
        self.owner = HumanUser.objects.create_user(email="skills@example.test", full_name="Owner")
        self.membership = OrganizationMembership.objects.create(
            organization=self.organization, user=self.owner, role=EmployeeRole.OWNER,
        )
        self.context = TenantContext.for_membership(self.membership)
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.owner)
        self.url = f"/api/v1/organizations/{self.organization.public_id}/skills/"
        self.agents = [self.make_agent(self.organization, f"agent-{i}") for i in range(2)]
        self.foreign_agent = self.make_agent(self.other, "foreign")

    def make_agent(self, organization, code):
        channel = Channel.objects.create(organization=organization, name=code, code=code)
        return AIAgent.objects.create(organization=organization, channel=channel, name=code)

    def config(self, **changes):
        return {"name": "Уточнение", "description": "Когда нужен номер", "instruction": "Спросите номер", "templates": [], **changes}

    def create_skill(self, **changes):
        response = self.client.post(self.url, {"requestId": str(uuid.uuid4()), "configuration": self.config(**changes)}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["skill"]

    def detail(self, skill):
        return f"{self.url}{skill['id']}/"

    def assignment(self, skill, agent):
        return f"{self.detail(skill)}agents/{agent.channel_id}/"
