"""Suppressed Gateway AI messages are retained for audit, never ordinary history."""

from django.test import TransactionTestCase

from chatballs.conversations.ai_history import conversation_history
from chatballs.conversations.gateway_delivery import GATEWAY_DELIVERY_COMMAND_REQUESTED
from chatballs.conversations.models import Message, MessageAuthor
from chatballs.conversations.serializers import last_messages_for
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.native_mirror.models import NativeMirrorPublication, PublicationStatus
from chatballs.native_mirror.supersession_fixture import NativeMirrorTurnFixture
from chatballs.testing import TenantAPIClient


class SuppressedPublicationVisibilityTests(NativeMirrorTurnFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.client = TenantAPIClient()
        self.client.login(
            username="mirror-supersede@example.com",
            password="temporary-password",
        )

    def _history(self, suffix=""):
        response = self.client.get(
            f"/api/v1/conversations/{self.conversation.id}/messages/{suffix}",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _list(self, suffix=""):
        response = self.client.get(f"/api/v1/conversations/{suffix}")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _publish_and_suppress(self):
        from unittest import mock

        turn = self._start()
        self._finish(turn, "Уникальный ответ, которого клиент не видел")
        ai = Message.objects.get(author_type=MessageAuthor.AI)
        event = OutboxEvent.objects.get(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
            aggregate_id=str(ai.id),
        )
        self.assertIn(ai.id, [x["id"] for x in self._history()["items"]])
        self._mirror()
        with mock.patch(
            "chatballs.conversations.gateway_event_handlers.send_delivery_command"
        ) as send:
            dispatch(event)
            send.assert_not_called()
        ai.refresh_from_db()
        return ai

    def test_suppressed_reply_hidden_from_open_history_and_cursor_windows(self):
        ai = self._publish_and_suppress()
        latest = self._history()
        self.assertNotIn(ai.id, [x["id"] for x in latest["items"]])
        self.assertFalse(any(
            x["text"] == ai.text for x in latest["items"]
        ))
        delta = self._history(f"?after={ai.id}")
        self.assertIn(ai.id, delta["removedIds"])
        self.assertTrue(any(x["author"] == "OPERATOR" for x in delta["items"]))
        before = self._history(f"?before={ai.id + 1}")
        self.assertNotIn(ai.id, [x["id"] for x in before["items"]])
        self.assertEqual(NativeMirrorPublication.objects.get(message=ai).status,
                         PublicationStatus.SUPPRESSED)

    def test_search_and_inbox_preview_ignore_suppressed_reply(self):
        ai = self._publish_and_suppress()
        matches = self._list("?q=Уникальный%20ответ")
        self.assertEqual(matches["items"], [])
        last = last_messages_for([self.conversation.id])[self.conversation.id]
        self.assertNotEqual(last.id, ai.id)
        self.assertEqual(last.author_type, MessageAuthor.OPERATOR)
        inbox = self._list()
        item = next(x for x in inbox["items"] if x["id"] == self.conversation.id)
        self.assertNotIn("Уникальный ответ", item["lastMessage"]["text"])

    def test_agent_context_does_not_recall_a_reply_the_customer_never_received(self):
        ai = self._publish_and_suppress()
        self._inbound("client-2")
        history = conversation_history(self.conversation, limit=30)
        flattened = [x["content"] for x in history]
        self.assertNotIn(ai.text, flattened)
        self.assertIn("Ответила в Telegram", flattened)

    def test_suppression_keeps_auditable_message_and_command_ids(self):
        ai = self._publish_and_suppress()
        self.assertTrue(Message.objects.filter(pk=ai.id).exists())
        self.assertEqual(ai.delivery_status, "suppressed")
        self.assertIsNotNone(ai.delivery_status_at)
        self.assertIsNotNone(ai.gateway_command_id)
        self.assertEqual(NativeMirrorPublication.objects.get(message=ai).status,
                         PublicationStatus.SUPPRESSED)
        self.conversation.refresh_from_db()
        visible_last = self.conversation.messages.exclude(
            native_mirror_publication__status=PublicationStatus.SUPPRESSED,
        ).order_by("-created_at", "-id").first()
        self.assertEqual(self.conversation.last_message_at, visible_last.created_at)

    def test_gateway_callback_cannot_resurrect_a_suppressed_reply(self):
        ai = self._publish_and_suppress()
        response = self.client.post(
            f"/api/v1/gateway/integrations/{self.integration.id}/delivery-status/",
            data={
                "schema": "intercom-gw.chatballs.delivery-status.v1",
                "source_id": "tg-native",
                "command_id": str(ai.gateway_command_id),
                "external_chat_id": "chat-1",
                "external_message_id": "unexpected-provider-id",
                "status": "provider_accepted",
                "occurred_at": "2026-10-12T12:00:00Z",
                "failure_kind": None,
            },
            format="json",
            HTTP_AUTHORIZATION="Bearer test",
        )
        self.assertEqual(response.status_code, 409)
        ai.refresh_from_db()
        self.assertEqual(ai.delivery_status, "suppressed")
        self.assertFalse(ai.external_id)
