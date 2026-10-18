"""VK native mirror acceptance and own-echo dedup using the existing tables."""

from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.models import AiTurnState, ControlMode, Conversation, Message, MessageAuthor
from chatballs.conversations.serializers import message_payload
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.native_mirror.models import NativeMirrorConversationState, NativeMirrorReceipt
from chatballs.native_mirror.replay import replay_pending_receipt
from chatballs.native_mirror.vk_adapter import VkNativeReply, observe_vk_reply
from chatballs.native_mirror.vk_outbound import record_vk_own_send
from chatballs.testing import system_tenant_context


class VkMirrorPersistenceTests(TestCase):
    def setUp(self):
        bootstrap_owner(email="vk-mirror@example.com", password="temporary-password")
        self.org = Organization.objects.get(slug="demo")
        self.context = system_tenant_context(self.org)
        self.channel = Channel.objects.create(
            organization=self.org, name="VK mirror test", code="vk-mirror",
        )
        self.integration = Integration.objects.create(
            organization=self.org, channel=self.channel,
            kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.VK,
            name="VK", secret="test", config={
                "bot_id": "42", "native_mirror_mode": "ENABLED",
            },
        )
        self.contact = self.org.contacts.create(name="Guest")
        self.conversation = self.make_conversation()

    def make_conversation(self):
        return Conversation.objects.create(
            organization=self.org, channel=self.channel,
            connection=self.integration, contact=self.contact,
            external_chat_id="77", control_mode=ControlMode.AI,
        )

    def reply(self, message_id="601", text="Native response"):
        return VkNativeReply(
            peer_id="77", message_id=message_id,
            text=text, occurred_at=1780000000,
        )

    def test_vk_native_is_displayed_once_without_staff_identity(self):
        before_mode = self.conversation.control_mode
        observe_vk_reply(self.integration, self.reply(), context=self.context)
        observe_vk_reply(self.integration, self.reply(), context=self.context)
        messages = list(Message.objects.filter(conversation=self.conversation))
        self.assertEqual(len(messages), 1)
        message = messages[0]
        self.assertEqual(message.author_type, MessageAuthor.OPERATOR)
        self.assertIsNone(message.author_user_id)
        self.assertEqual(message_payload(message)["authorName"], "VK Native")
        self.assertEqual(NativeMirrorReceipt.objects.count(), 1)
        self.assertEqual(NativeMirrorConversationState.objects.get().revision, 1)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, before_mode)

    def test_chatballs_own_echo_is_not_mirrored(self):
        record_vk_own_send(self.integration, peer_id="77", provider_id=800)
        observe_vk_reply(self.integration, self.reply("800"), context=self.context)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(NativeMirrorReceipt.objects.count(), 1)
        self.assertFalse(NativeMirrorConversationState.objects.exists())

    def test_pending_reply_is_replayed_when_conversation_appears(self):
        self.conversation.delete()
        observe_vk_reply(self.integration, self.reply("603"), context=self.context)
        self.assertEqual(Message.objects.count(), 0)
        receipt = NativeMirrorReceipt.objects.get()
        self.assertEqual(receipt.status, "PENDING")
        self.conversation = self.make_conversation()
        replay_pending_receipt(receipt_id=receipt.id, context=self.context)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(Message.objects.get().author_user_id, None)
        self.assertEqual(NativeMirrorReceipt.objects.get().status, "STORED")

    def test_two_different_vk_message_ids_are_not_text_deduplicated(self):
        observe_vk_reply(self.integration, self.reply("604"), context=self.context)
        observe_vk_reply(self.integration, self.reply("605"), context=self.context)
        self.assertEqual(Message.objects.count(), 2)
        self.assertEqual(NativeMirrorConversationState.objects.get().revision, 2)

    def test_native_reply_supersedes_existing_ai_turn_without_takeover(self):
        pending = Message.objects.create(
            conversation=self.conversation,
            author_type=MessageAuthor.CONTACT, text="Question",
            ai_turn_state=AiTurnState.RUNNING,
        )
        observe_vk_reply(self.integration, self.reply("608"), context=self.context)
        pending.refresh_from_db()
        self.conversation.refresh_from_db()
        self.assertEqual(pending.ai_turn_state, AiTurnState.DONE)
        self.assertEqual(self.conversation.control_mode, ControlMode.AI)
        self.assertEqual(NativeMirrorConversationState.objects.get().revision, 1)

    def test_self_echo_does_not_supersede_ai_turn(self):
        pending = Message.objects.create(
            conversation=self.conversation,
            author_type=MessageAuthor.CONTACT, text="Question",
            ai_turn_state=AiTurnState.RUNNING,
        )
        record_vk_own_send(self.integration, peer_id="77", provider_id=609)
        observe_vk_reply(self.integration, self.reply("609"), context=self.context)
        pending.refresh_from_db()
        self.assertEqual(pending.ai_turn_state, AiTurnState.RUNNING)
        self.assertFalse(NativeMirrorConversationState.objects.exists())

    def test_shadow_does_not_create_message_or_receipt(self):
        self.integration.config = {"bot_id": "42", "native_mirror_mode": "SHADOW"}
        observe_vk_reply(self.integration, self.reply("607"), context=self.context)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(NativeMirrorReceipt.objects.count(), 0)
