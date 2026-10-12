from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from chatballs.ai.assistance_behavior_base import AssistanceBehaviorData
from chatballs.conversations.realtime import conversation_group
from chatballs.identity.models import OrganizationMembership
from chatballs.realtime import publish
from chatballs_backend.asgi_app import application


class AssistanceRealtimeTests(AssistanceBehaviorData, TransactionTestCase):
    def setUp(self):
        self.enterContext(override_settings(CHANNEL_LAYERS={"default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [settings.CACHES["default"]["LOCATION"]],
                       "prefix": "chatballs-assistance-tests"},
        }}))
        super().setUp()

    async def socket(self):
        socket = WebsocketCommunicator(application,
            f"/ws/organizations/{self.organization.public_id}/conversations/")
        socket.scope["user"] = self.member.user
        connected, _ = await socket.connect(timeout=5)
        self.assertTrue(connected)
        await socket.send_json_to({"type": "watch", "conversationId": self.conversation.pk})
        self.assertEqual((await socket.receive_json_from(timeout=5))["type"], "watching")
        return socket

    async def test_realtime_invalidation_rechecks_active_reply_rights_on_every_delivery(self):
        socket = await self.socket()
        payload = {"type": "reply_assistance.changed", "conversationId": self.conversation.pk,
                   "attemptId": "opaque-id"}
        await database_sync_to_async(publish)(conversation_group(self.conversation.pk), payload)
        self.assertEqual(await socket.receive_json_from(timeout=5), payload)
        await database_sync_to_async(self.revoke)()
        await database_sync_to_async(publish)(conversation_group(self.conversation.pk), payload)
        self.assertTrue(await socket.receive_nothing(timeout=0.3))
        await socket.disconnect()

    def revoke(self):
        OrganizationMembership.objects.filter(pk=self.member.pk).update(blocked_at=timezone.now())
