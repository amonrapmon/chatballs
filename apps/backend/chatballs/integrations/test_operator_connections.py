"""Agent-free connections, public sessions and shared-route compatibility."""

from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from chatballs.ai.models import AIAgent
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import HumanUser, Organization, OrganizationMembership
from chatballs.integrations.models import Integration
from chatballs.testing import TenantAPIClient


class OperatorConnectionTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Org", slug="operator-connections", operation_mode="OPERATORS_ONLY")
        self.user = HumanUser.objects.create_user(email="owner@operator-connections.test")
        OrganizationMembership.objects.create(organization=self.organization, user=self.user, role="OWNER")
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.user)
        self.group = EmployeeGroup.objects.create(organization=self.organization, name="Team")
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings = override_settings(MEDIA_ROOT=self.media.name)
        settings.enable()
        self.addCleanup(settings.disable)

    def create(self, provider, **kwargs):
        config = {"allowedOrigins": ["https://example.com"]} if provider == "WEB" else {}
        if provider == "EMAIL":
            config = {"email": "support@example.com", "imapHost": "imap.example.com", "smtpHost": "smtp.example.com"}
        return self.client.post("/api/v1/integrations/", {
            "name": provider, "provider": provider, "secret": "token", "config": config,
            "groupId": self.group.pk, **kwargs,
        }, format="json")

    def test_supported_connections_create_independent_routes_without_agents(self):
        ids = set()
        for provider in ["TELEGRAM", "MAX", "VK", "EMAIL", "WEB"]:
            with self.subTest(provider=provider):
                response = self.create(provider)
                self.assertEqual(response.status_code, 201, response.data)
                connection = Integration.objects.get(pk=response.data["integration"]["id"])
                self.assertIsNotNone(connection.channel_id)
                self.assertEqual(connection.channel.group_id, self.group.pk)
                ids.add(connection.channel_id)
        self.assertEqual(len(ids), 5)
        self.assertFalse(AIAgent.objects.exists())
        self.assertEqual(self.client.get("/api/v1/agents/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/agents/directory/").status_code, 200)
        self.assertFalse(AIAgent.objects.exists())

    def test_group_is_tenant_scoped_and_shared_route_is_not_silently_split(self):
        foreign = Organization.objects.create(name="Other", slug="foreign-group")
        foreign_group = EmployeeGroup.objects.create(organization=foreign, name="Other")
        self.assertEqual(self.create("TELEGRAM", groupId=foreign_group.pk).status_code, 400)
        response = self.create("TELEGRAM")
        first = Integration.objects.get(pk=response.data["integration"]["id"])
        second = self.create("MAX", channelId=first.channel_id)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second.data["integration"]["channel"]["id"], first.channel_id)
        response = self.client.patch(f"/api/v1/integrations/{first.pk}/", {"groupId": None}, format="json")
        self.assertEqual(response.status_code, 400)
        first.refresh_from_db()
        self.assertEqual(first.channel.group_id, self.group.pk)
        self.assertEqual(first.channel.connections.count(), 2)

    def test_published_widget_accepts_text_file_voice_and_history_without_agent(self):
        response = self.create("WEB")
        self.assertEqual(response.status_code, 201, response.data)
        connection = Integration.objects.get(pk=response.data["integration"]["id"])
        widget = connection.web_chat_widget
        key = widget.public_key
        public = APIClient()
        config = public.get("/api/v1/webchat/config/", {"widgetKey": key, "hostOrigin": "https://example.com"})
        self.assertTrue(config.data["available"])
        self.assertFalse(config.data["autonomous"])
        session = public.post("/api/v1/webchat/session/", {
            "widgetKey": key, "hostOrigin": "https://example.com", "agentId": 999, "operationMode": "AI_AGENTS",
        }, format="json")
        self.assertEqual(session.status_code, 201, session.data)
        headers = {"Authorization": f"Bearer {session.data['token']}"}
        posted = public.post("/api/v1/webchat/messages/", {"text": "Hello"}, format="json", headers=headers)
        self.assertEqual(posted.status_code, 201)
        upload = public.post("/api/v1/webchat/messages/", {
            "file": SimpleUploadedFile("note.txt", b"content", content_type="text/plain"),
        }, format="multipart", headers=headers)
        self.assertEqual(upload.status_code, 201, upload.data)
        voice = public.post("/api/v1/webchat/messages/", {
            "audio": SimpleUploadedFile("voice.webm", b"audio", content_type="audio/webm"), "duration": 2,
        }, format="multipart", headers=headers)
        self.assertEqual(voice.status_code, 201, voice.data)
        history = public.get("/api/v1/webchat/messages/", headers=headers)
        self.assertEqual(history.data["state"], "waiting")
        self.assertFalse(history.data["thinking"])
        self.assertFalse(history.data["autonomous"])
        self.assertEqual(len(history.data["messages"]), 3)
        self.assertTrue(history.data["messages"][-1]["hasAudio"])
        self.assertFalse(AIAgent.objects.exists())
        denied = public.post("/api/v1/webchat/session/", {
            "widgetKey": key, "hostOrigin": "https://evil.example",
        }, format="json")
        self.assertEqual(denied.status_code, 404)
        connection.refresh_from_db()
        self.assertEqual(connection.web_chat_widget.public_key, key)
