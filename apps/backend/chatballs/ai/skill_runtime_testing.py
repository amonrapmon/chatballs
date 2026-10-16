"""Skill runtime setup confined to the isolated test database."""

from unittest.mock import patch

from chatballs.ai.models import AIAgentStatus
from chatballs.ai.pseudonymization import Pseudonymizer
from chatballs.ai.skills_models import AgentSkill, Skill
from chatballs.ai.skills_test_support import SkillsSetup
from chatballs.ai.turn import plan_chat
from chatballs.tenancy.database import tenant_atomic


class SkillRuntimeSetup(SkillsSetup):
    def setUp(self):
        super().setUp()
        self.agent = self.agents[0]
        self.agent.status = AIAgentStatus.ACTIVE
        self.agent.save(update_fields=["status"])
        self.skill = self.attach()
        self.client.set_tenant(self.organization)
        self.chat_url = f"/api/v1/agents/{self.agent.channel_id}/test-chat/"

    def attach(self, *, agent=None, **changes):
        agent = agent or self.agent
        skill = Skill.objects.create(
            organization=agent.organization,
            **{"name": "Уточнение обращения", "description": "Когда не указан номер обращения",
               "instruction": "Перед поиском запросите недостающий номер обращения.", **changes},
        )
        AgentSkill.objects.create(organization=agent.organization, agent=agent, skill=skill)
        return skill

    def plan(self, provider, *, pseudonymizer=None):
        with tenant_atomic(self.context), patch("chatballs.ai.invocation.get_provider", return_value=provider):
            return plan_chat(agent=self.agent, message="Помогите с обращением",
                             pseudonymizer=pseudonymizer or Pseudonymizer())
