from django.test import TestCase

from chatballs.ai.assistance_test_base import AssistanceTestData
from chatballs.ai.models import AIAgentStatus
from chatballs.channels.models import Channel
from chatballs.conversations.models import Conversation
from chatballs.integrations.models import (
    Integration,
    IntegrationKind,
    IntegrationProvider,
)
from chatballs.testing import TenantAPIClient


class AssistanceSettingsTests(AssistanceTestData, TestCase):
    def setUp(self):
        super().setUp()
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.member.user)
        self.url = (
            f"/api/v1/organizations/{self.organization.public_id}/agents/{self.agent.channel_id}/"
        )

    def test_setting_and_automatic_answers_are_independent(self):
        self.assertFalse(self.agent.assistance_enabled)
        provider = Integration.objects.create(
            organization=self.organization, name="Provider", kind=IntegrationKind.LLM_PROVIDER,
            provider=IntegrationProvider.DEMO, config={"default_model": "demo"},
        )
        response = self.client.patch(
            self.url, {"assistanceEnabled": True, "providerIntegrationId": provider.id,
                       "model": "existing-model", "modelParams": {"temperature": 0.3}},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["agent"]["assistanceEnabled"])
        self.assertEqual(response.json()["agent"]["aiStatus"], AIAgentStatus.DRAFT)
        for active in (True, False):
            action = "activate/" if active else "deactivate/"
            response = self.client.post(self.url + action, {}, format="json")
            self.assertEqual(response.status_code, 200, response.content)
            self.assertTrue(response.json()["agent"]["assistanceEnabled"])
        response = self.client.patch(self.url, {"instructions": "legacy update"}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.agent.refresh_from_db()
        self.assertTrue(self.agent.assistance_enabled)
        self.assertEqual(self.agent.status, AIAgentStatus.DISABLED)
        self.assertEqual(self.agent.provider_integration, provider)
        self.assertEqual(self.agent.model, "existing-model")
        self.assertEqual(self.agent.model_params, {"temperature": 0.3})
        # Выключение помощи у активного AI не выключает автоответы.
        activated = self.client.post(self.url + "activate/", {}, format="json")
        self.assertEqual(activated.status_code, 200, activated.content)
        response = self.client.patch(self.url, {"assistanceEnabled": False}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["agent"]["aiStatus"], AIAgentStatus.ACTIVE)
        self.assertFalse(response.json()["agent"]["assistanceEnabled"])

    def test_conversation_card_reports_whether_assistance_is_enabled(self):
        url = (
            f"/api/v1/organizations/{self.organization.public_id}"
            f"/conversations/{self.conversation.pk}/"
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.json()["conversation"]["replyAssistanceEnabled"], False)
        self.agent.assistance_enabled = True
        self.agent.save(update_fields=["assistance_enabled"])
        response = self.client.get(url)
        self.assertIs(response.json()["conversation"]["replyAssistanceEnabled"], True)
        # Канал без агента: помощи нет, карточка открывается как обычно.
        self.agent.delete()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIs(response.json()["conversation"]["replyAssistanceEnabled"], False)

    def test_boolean_is_strict_and_foreign_card_is_inaccessible(self):
        for value in (None, "true", 1, [], {}):
            with self.subTest(value=value):
                response = self.client.patch(self.url, {"assistanceEnabled": value}, format="json")
                self.assertEqual(response.status_code, 400, response.content)
        other, _member, foreign_agent, _conversation = self.create_tenant("assist-other")
        response = self.client.patch(
            self.url.replace(str(self.organization.public_id), str(other.public_id)),
            {"assistanceEnabled": True}, format="json",
        )
        self.assertIn(response.status_code, (403, 404))
        response = self.client.patch(
            f"/api/v1/organizations/{self.organization.public_id}/agents/{foreign_agent.channel_id}/",
            {"assistanceEnabled": True}, format="json",
        )
        self.assertEqual(response.status_code, 404, response.content)
        self.agent.refresh_from_db()
        self.assertFalse(self.agent.assistance_enabled)

    def test_attempt_blocks_agent_deletion_after_conversation_transfer(self):
        self.attempt()
        destination = Channel.objects.create(
            organization=self.organization, name="Destination", code="destination",
        )
        Conversation.objects.filter(pk=self.conversation.pk).update(channel=destination)
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["blockers"], [{"type": "replyAssistanceAttempts", "count": 1}])
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.reply_assistance_attempts.count(), 1)
