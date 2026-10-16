import uuid
from dataclasses import replace

from django.test import TestCase

from chatballs.ai.skills_models import AgentSkill, Skill
from chatballs.ai.skills_queries import library
from chatballs.ai.skills_service import save_configuration, set_assignment
from chatballs.ai.skills_test_support import SkillsSetup
from chatballs.ai.skills_validation import SkillError
from chatballs.identity.models import EmployeeRole, HumanUser, OrganizationMembership
from chatballs.tenancy.context import TenantContext
from chatballs.testing import TenantAPIClient


class SkillAccessTests(SkillsSetup, TestCase):
    def test_owner_admin_manage_employee_supervisor_cannot_access(self):
        skill = self.create_skill()
        for role in (EmployeeRole.ADMIN, EmployeeRole.EMPLOYEE, EmployeeRole.SUPERVISOR):
            user = HumanUser.objects.create_user(email=f"{role}@example.test")
            member = OrganizationMembership.objects.create(organization=self.organization, user=user, role=role)
            client = TenantAPIClient()
            client.force_authenticate(user)
            requests = [
                lambda client=client: client.get(self.url),
                lambda client=client: client.get(self.detail(skill)),
                lambda client=client: client.get(self.detail(skill) + "deletion/"),
                lambda client=client: client.post(self.url, {"requestId": str(uuid.uuid4()), "configuration": self.config()}, format="json"),
                lambda client=client: client.put(self.detail(skill), {"requestId": str(uuid.uuid4()), "expectedRevision": 1, "configuration": self.config()}, format="json"),
                lambda client=client: client.put(self.assignment(skill, self.agents[0]), {"expectedRevision": 2}, format="json"),
                lambda client=client: client.delete(self.assignment(skill, self.agents[0]), {"expectedRevision": 3}, format="json"),
                lambda client=client: client.delete(self.detail(skill), {"expectedRevision": 4}, format="json"),
            ]
            # ADMIN traverses a complete lifecycle; others cannot even read.
            if role == EmployeeRole.ADMIN:
                for call, status in zip(requests, (200, 200, 200, 201, 200, 200, 200, 204), strict=True):
                    result = call()
                    self.assertEqual(result.status_code, status, result.content)
            else:
                for call in requests:
                    result = call()
                    self.assertEqual(result.status_code, 403, result.content)
                    self.assertEqual(result.json()["code"], "forbidden")
                context = TenantContext.for_membership(member)
                for call in (
                    lambda context=context: library(context),
                    lambda context=context: save_configuration(context=context, raw=self.config(), request_id=uuid.uuid4()),
                    lambda context=context: set_assignment(context=context, public_id=uuid.uuid4(), agent_id=self.agents[0].channel_id, enabled=True, revision=1),
                ):
                    with self.assertRaises(SkillError) as error:
                        call()
                    self.assertEqual(error.exception.status_code, 403)

    def test_foreign_tenant_and_forged_context_cannot_reach_configuration(self):
        skill = self.create_skill()
        foreign_user = HumanUser.objects.create_user(email="foreign@example.test")
        member = OrganizationMembership.objects.create(organization=self.other, user=foreign_user, role=EmployeeRole.OWNER)
        client = TenantAPIClient()
        client.force_authenticate(foreign_user)
        other_url = f"/api/v1/organizations/{self.other.public_id}/skills/"
        self.assertEqual(client.get(other_url).json()["total"], 0)
        self.assertEqual(client.get(self.detail(skill)).status_code, 404)
        self.assertEqual(client.get(f"{other_url}{skill['id']}/").status_code, 404)
        for method in (self.client.put, self.client.delete):
            result = method(self.assignment(skill, self.foreign_agent), {"expectedRevision": 1}, format="json")
            self.assertEqual(result.status_code, 404)
        self.assertFalse(AgentSkill.objects.exists())
        with self.assertRaises(SkillError):
            library(replace(TenantContext.for_membership(member), organization=self.organization))
        self.assertEqual(Skill.objects.get().revision, 1)

    def test_anonymous_and_public_widget_have_no_library(self):
        self.create_skill()
        client = TenantAPIClient()
        self.assertIn(client.get(self.url).status_code, (403, 404))
        for path in ("/api/v1/skills/", "/api/v1/webchat/skills/", "/api/v1/ai/skills/"):
            self.assertEqual(client.get(path).status_code, 404)
