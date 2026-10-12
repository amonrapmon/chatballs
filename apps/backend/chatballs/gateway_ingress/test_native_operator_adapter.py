"""Mode-gated TG/MAX native events through the existing Gateway HTTP contract."""

import uuid
from datetime import UTC, datetime
from unittest import mock

from django.test import TestCase

from chatballs.conversations.models import (
    AiTurnState, ControlMode, Conversation, ExpectedResponder, Message, MessageAuthor,
)
from chatballs.events.models import InboxEvent, OutboxEvent
from chatballs.gateway_ingress import test_operator_mirror as legacy_tests
from chatballs.identity.models import OrganizationMembership
from chatballs.native_mirror.models import (
    MirrorReceiptStatus, NativeMirrorConversationState, NativeMirrorReceipt,
)


def _attested_payload(**overrides):
    return {
        **legacy_tests._payload(**overrides),
        "origin": {"provider_event_type": "outgoingMessageReceived"},
    }


class GatewayNativeOperatorModesTests(TestCase):
    # Reuse existing Gateway-auth, service-account and Conversation fixtures
    # without inheriting the legacy test methods.
    endpoint_template = legacy_tests.GatewayOperatorMirrorTests.endpoint_template
    _post = legacy_tests.GatewayOperatorMirrorTests._post

    def setUp(self):
        legacy_tests.GatewayOperatorMirrorTests.setUp(self)

    def mode(self, value):
        self.integration.config = {
            **self.integration.config, "native_mirror_mode": value,
        }
        self.integration.save(update_fields=["config"])

    def test_default_legacy_preserves_takeover_without_new_receipt(self):
        response = self._post()
        self.assertEqual(response.status_code, 202)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, ControlMode.HUMAN)
        self.assertEqual(InboxEvent.objects.count(), 1)
        self.assertFalse(NativeMirrorReceipt.objects.exists())

    def test_disabled_ignores_native_event_without_persisting(self):
        self.mode("DISABLED")
        self.assertEqual(self._post(_attested_payload()).status_code, 202)
        self.assertFalse(Message.objects.exists())
        self.assertFalse(InboxEvent.objects.exists())
        self.assertFalse(NativeMirrorReceipt.objects.exists())
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, ControlMode.AI)

    def test_shadow_validates_source_and_never_changes_dialogue_or_ai(self):
        self.mode("SHADOW")
        active = Message.objects.create(
            conversation=self.conversation, author_type=MessageAuthor.CONTACT,
            text="Вопрос", ai_turn_state=AiTurnState.RUNNING,
        )
        with mock.patch(
            "chatballs.gateway_ingress.native_operator_adapter.logger.info"
        ) as log:
            self.assertEqual(self._post(_attested_payload()).status_code, 202)
            self.assertEqual(self._post().status_code, 202)  # old v1 remains observable
            self.assertTrue(log.called)
        active.refresh_from_db()
        self.assertEqual(active.ai_turn_state, AiTurnState.RUNNING)
        self.assertEqual(Message.objects.count(), 1)
        self.assertFalse(InboxEvent.objects.exists())
        self.assertFalse(NativeMirrorReceipt.objects.exists())
        self.assertFalse(NativeMirrorConversationState.objects.exists())
        self.assertFalse(OutboxEvent.objects.exists())
        self.assertEqual(
            self._post(_attested_payload(source_id="wrong")).status_code, 409
        )

    def test_enabled_rejects_unattested_and_api_originated_events(self):
        self.mode("ENABLED")
        self.assertEqual(self._post().status_code, 409)
        p = _attested_payload()
        p["origin"]["provider_event_type"] = "outgoingAPIMessageReceived"
        self.assertEqual(self._post(p).status_code, 409)
        self.assertEqual(
            self._post(_attested_payload(occurred_at=None)).status_code, 400
        )
        self.assertFalse(Message.objects.exists())
        self.assertFalse(NativeMirrorReceipt.objects.exists())

    def test_enabled_records_native_reply_without_human_takeover(self):
        self.mode("ENABLED")
        active = Message.objects.create(
            conversation=self.conversation, author_type=MessageAuthor.CONTACT,
            text="Вопрос", ai_turn_state=AiTurnState.RUNNING,
        )
        response = self._post(_attested_payload())
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"accepted": True})
        new = Message.objects.get(author_type=MessageAuthor.OPERATOR)
        self.assertEqual(new.author_user_id, self.native_user.id)
        self.assertEqual(new.text, "Нативный ответ")
        self.assertEqual(new.external_reply_to_id, "provider-message-0")
        self.assertEqual(
            new.external_occurred_at, datetime(2026, 9, 20, 12, 34, 56, tzinfo=UTC),
        )
        active.refresh_from_db()
        self.assertEqual(active.ai_turn_state, AiTurnState.DONE)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, ControlMode.AI)
        self.assertEqual(self.conversation.expected_responder, ExpectedResponder.AI)
        self.assertIsNotNone(self.conversation.waiting_since)
        self.assertEqual(NativeMirrorConversationState.objects.get().revision, 1)
        self.assertEqual(NativeMirrorReceipt.objects.get().status, MirrorReceiptStatus.STORED)
        self.assertFalse(InboxEvent.objects.exists())
        self.assertFalse(OutboxEvent.objects.exists())

    def test_enabled_duplicate_uses_durable_receipt_not_legacy_inbox(self):
        self.mode("ENABLED")
        self.assertEqual(self._post(_attested_payload()).status_code, 202)
        self.assertEqual(self._post(_attested_payload()).status_code, 202)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(NativeMirrorReceipt.objects.count(), 1)
        self.assertEqual(NativeMirrorConversationState.objects.get().revision, 1)
        self.assertFalse(InboxEvent.objects.exists())

    def test_enabled_missing_conversation_is_durable_and_replayable(self):
        self.mode("ENABLED")
        self.conversation.delete()
        p = _attested_payload()
        self.assertEqual(self._post(p).status_code, 202)
        receipt = NativeMirrorReceipt.objects.get()
        self.assertEqual(receipt.status, MirrorReceiptStatus.PENDING)
        self.assertEqual(receipt.pending_text, "Нативный ответ")
        self.conversation = Conversation.objects.create(
            organization=self.organization, channel=self.channel,
            connection=self.integration, contact=self.contact,
            external_chat_id="chat-1", control_mode=ControlMode.AI,
        )
        self.assertEqual(self._post(p).status_code, 202)
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, MirrorReceiptStatus.STORED)
        self.assertEqual(Message.objects.count(), 1)

    def test_enabled_conflicting_redelivery_is_rejected_without_side_effect(self):
        self.mode("ENABLED")
        p = _attested_payload()
        self.assertEqual(self._post(p).status_code, 202)
        conflict = _attested_payload()
        conflict["message"]["text"] = "changed"
        self.assertEqual(self._post(conflict).status_code, 409)
        self.assertEqual(Message.objects.count(), 1)

    def test_enabled_correlated_own_message_is_not_mirrored_or_superseded(self):
        self.mode("ENABLED")
        Message.objects.create(
            conversation=self.conversation, author_type=MessageAuthor.AI,
            text="Ответ Chatballs", external_id="provider-message-1",
            gateway_command_id=uuid.uuid4(),
        )
        p = _attested_payload()
        self.assertEqual(self._post(p).status_code, 202)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(
            NativeMirrorReceipt.objects.get().status, MirrorReceiptStatus.SELF_ECHO
        )
        self.assertFalse(NativeMirrorConversationState.objects.exists())

    def test_enabled_requires_configured_bridge_membership(self):
        self.mode("ENABLED")
        OrganizationMembership.objects.filter(user=self.native_user).delete()
        self.assertEqual(self._post(_attested_payload()).status_code, 409)
        self.assertFalse(NativeMirrorReceipt.objects.exists())

    def test_enabled_wrong_bearer_or_source_cannot_save_receipt(self):
        self.mode("ENABLED")
        self.assertEqual(
            self._post(_attested_payload(), secret="wrong").status_code, 401
        )
        self.assertEqual(
            self._post(_attested_payload(source_id="other")).status_code, 409
        )
        self.assertFalse(NativeMirrorReceipt.objects.exists())
