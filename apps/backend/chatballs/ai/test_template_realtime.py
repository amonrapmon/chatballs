from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase, override_settings

from chatballs.ai.skill_runtime_testing import SkillRuntimeSetup
from chatballs.ai.skill_templates.engine import render_template
from chatballs.ai.template_runtime_testing import reply_template
from chatballs.conversations.models import Contact, Conversation, Message
from chatballs.tenancy.database import tenant_atomic
from chatballs_backend.asgi_app import application


@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
class TemplateRealtimeTests(SkillRuntimeSetup, TransactionTestCase):
    def setUp(self):
        super().setUp()
        contact = Contact.objects.create(organization=self.organization, name="Customer")
        self.conversation = Conversation.objects.create(
            organization=self.organization, channel=self.agent.channel, contact=contact,
        )

    @database_sync_to_async
    def save_snapshot(self):
        rendered = render_template(reply_template(), {"title": "Status", "amount": 0, "active": False}, language="en")
        with tenant_atomic(self.context):
            message = Message.objects.create(
                conversation=self.conversation, author_type="AI", text=rendered["text"],
                content_html=rendered["contentHtml"], format_version=1,
                presentation=rendered["presentation"], delivery_representation="html",
                template_snapshot={"id": reply_template()["id"], "name": "Status", "skillId": str(self.skill.public_id), "skillRevision": 1},
            )
        return message.pk, rendered

    @database_sync_to_async
    def read_history(self):
        return self.client.get(f"/api/v1/conversations/{self.conversation.pk}/messages/")

    async def test_websocket_invalidation_refetches_the_same_authorized_snapshot(self):
        socket = WebsocketCommunicator(
            application, f"/ws/organizations/{self.organization.public_id}/conversations/",
        )
        socket.scope["user"] = self.owner
        self.assertTrue((await socket.connect(timeout=5))[0])
        try:
            await socket.send_json_to({"type": "watch", "conversationId": self.conversation.pk})
            self.assertEqual((await socket.receive_json_from(timeout=5))["type"], "watching")
            identifier, rendered = await self.save_snapshot()
            events = [await socket.receive_json_from(timeout=5) for _ in range(2)]
            self.assertEqual({event["type"] for event in events}, {"inbox.changed", "conversation.changed"})
            self.assertNotIn("contentHtml", repr(events))
            response = await self.read_history()
            self.assertEqual(response.status_code, 200, response.content)
            message = next(item for item in response.json()["items"] if item["id"] == identifier)
            self.assertEqual(message["contentHtml"], rendered["contentHtml"])
            self.assertEqual(message["presentation"], rendered["presentation"])
            self.assertNotIn("ai_delivery", message)
        finally:
            await socket.disconnect()
