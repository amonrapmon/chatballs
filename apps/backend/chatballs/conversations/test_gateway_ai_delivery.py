"""Gateway AI outbound uses the existing durable Message delivery outbox."""

from unittest import mock

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from chatballs.ai.models import AIAgent, AIAgentStatus
from chatballs.ai.runtime import HANDOFF_TOKEN
from chatballs.channels.models import Channel
from chatballs.conversations.ai_turn import AI_TURN_REQUESTED
from chatballs.conversations.gateway_delivery import (
    GATEWAY_DELIVERY_COMMAND_REQUESTED,
    enqueue_gateway_delivery,
)
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import AiTurnState, ControlMode, Message, MessageAuthor, SystemEvent
from chatballs.conversations.transports.base import InboundMessage
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.testing import ai_answer, ai_failure, run_pending_ai_turns, system_tenant_context
from chatballs.tenancy.database import tenant_atomic


class GatewayAiOutboundTests(TestCase):
    def setUp(self) -> None:
        bootstrap_owner(email="gateway-ai@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.channel = Channel.objects.create(
            organization=self.organization, code="gateway-ai", name="Gateway AI"
        )
        AIAgent.objects.create(
            channel=self.channel,
            name="Agent",
            model="openai/gpt-4o-mini",
            status=AIAgentStatus.ACTIVE,
        )
        self.integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.GATEWAY,
            name="Gateway AI source",
            secret="gateway-secret",
            config={"source_id": "tg-studio-main", "base_url": "https://gateway.example.test/"},
            channel=self.channel,
        )
        self.inbound = InboundMessage(
            external_id="inbound-1",
            user_id="user-1",
            chat_id="chat-1",
            text="Здравствуйте",
            display_name="Гость",
        )

    def _events(self):
        return OutboxEvent.objects.filter(event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED)

    def _ai_message(self):
        return Message.objects.get(author_type=MessageAuthor.AI)

    def test_ai_success_creates_one_ai_message_and_durable_command(self) -> None:
        with (
            ai_answer("Ответ AI"),
            mock.patch("chatballs.conversations.transports.send_reply") as direct_send,
        ):
            ingest_inbound(self.integration, self.inbound)
            self.assertEqual(run_pending_ai_turns(), 1)
        direct_send.assert_not_called()
        message = self._ai_message()
        self.assertIsNone(message.author_user)
        self.assertEqual(message.text, "Ответ AI")
        self.assertEqual(message.delivery_status, "queued")
        self.assertIsNotNone(message.gateway_command_id)
        self.assertFalse(Message.objects.filter(author_type=MessageAuthor.OPERATOR).exists())
        self.assertEqual(self._events().count(), 1)
        event = self._events().get()
        self.assertEqual(event.aggregate_id, str(message.id))
        command = event.payload["command"]
        self.assertEqual(command["command_id"], str(message.gateway_command_id))
        self.assertEqual(command["source_id"], "tg-studio-main")
        self.assertEqual(command["recipient"]["external_chat_id"], "chat-1")
        self.assertEqual(command["recipient"]["external_user_id"], "user-1")
        self.assertEqual(command["message"], {"kind": "text", "text": "Ответ AI"})
        self.assertEqual(
            Message.objects.get(author_type=MessageAuthor.CONTACT).ai_turn_state,
            AiTurnState.DONE,
        )

    def test_failure_fallback_is_ai_message_and_queues_delivery(self) -> None:
        with (
            ai_failure(),
            mock.patch("chatballs.conversations.transports.send_reply") as direct_send,
        ):
            ingest_inbound(self.integration, self.inbound)
            run_pending_ai_turns()
        direct_send.assert_not_called()
        message = self._ai_message()
        self.assertTrue(message.text)
        self.assertEqual(message.delivery_status, "queued")
        self.assertEqual(self._events().count(), 1)
        self.assertEqual(self._events().get().aggregate_id, str(message.id))
        self.assertEqual(
            Message.objects.get(author_type=MessageAuthor.CONTACT).ai_turn_state,
            AiTurnState.FAILED,
        )
        self.assertEqual(self.channel.conversations.get().control_mode, ControlMode.PAUSED)

    def test_handoff_with_text_sends_only_visible_reply(self) -> None:
        with ai_answer(f"Вот детали {HANDOFF_TOKEN}"):
            ingest_inbound(self.integration, self.inbound)
            run_pending_ai_turns()
        self.assertEqual(self._ai_message().text, "Вот детали")
        self.assertEqual(self._events().get().payload["command"]["message"]["text"], "Вот детали")
        self.assertTrue(
            Message.objects.filter(system_event=SystemEvent.AI_HANDED_OVER).exists()
        )
        self.assertEqual(self.channel.conversations.get().control_mode, ControlMode.PAUSED)

    def test_handoff_without_text_creates_no_empty_command(self) -> None:
        with ai_answer(HANDOFF_TOKEN):
            ingest_inbound(self.integration, self.inbound)
            run_pending_ai_turns()
        message = self._ai_message()
        self.assertEqual(message.text, "")
        self.assertIsNone(message.gateway_command_id)
        self.assertFalse(self._events().exists())
        self.assertTrue(Message.objects.filter(system_event=SystemEvent.AI_HANDED_OVER).exists())

    def test_enqueue_error_rolls_back_ai_message_and_terminal_state(self) -> None:
        ingest_inbound(self.integration, self.inbound)
        with (
            ai_answer("Не доставлять"),
            mock.patch(
                "chatballs.conversations.gateway_delivery.enqueue_event",
                side_effect=RuntimeError("outbox unavailable"),
            ),
            self.assertRaises(RuntimeError),
        ):
            run_pending_ai_turns()
        self.assertFalse(Message.objects.filter(author_type=MessageAuthor.AI).exists())
        self.assertFalse(self._events().exists())
        self.assertEqual(
            Message.objects.get(author_type=MessageAuthor.CONTACT).ai_turn_state,
            AiTurnState.RUNNING,
        )

    def test_repeated_ai_event_does_not_create_second_command(self) -> None:
        with ai_answer("Единственный ответ"):
            ingest_inbound(self.integration, self.inbound)
            event = OutboxEvent.objects.get(event_type=AI_TURN_REQUESTED)
            dispatch(event)
            dispatch(event)
        self.assertEqual(Message.objects.filter(author_type=MessageAuthor.AI).count(), 1)
        self.assertEqual(self._events().count(), 1)

    def test_enqueue_existing_message_is_idempotent(self) -> None:
        with ai_answer("Ответ AI"):
            ingest_inbound(self.integration, self.inbound)
            run_pending_ai_turns()
        message = self._ai_message()
        old_command_id = message.gateway_command_id
        with tenant_atomic(system_tenant_context(self.organization)):
            enqueue_gateway_delivery(
                context=system_tenant_context(self.organization), message=message
            )
        message.refresh_from_db()
        self.assertEqual(message.gateway_command_id, old_command_id)
        self.assertEqual(self._events().count(), 1)

    def test_delivery_status_callback_updates_original_ai_message(self) -> None:
        with ai_answer("Ответ AI"):
            ingest_inbound(self.integration, self.inbound)
            run_pending_ai_turns()
        message = self._ai_message()
        response = APIClient().post(
            f"/api/v1/gateway/integrations/{self.integration.id}/delivery-status/",
            data={
                "schema": "intercom-gw.chatballs.delivery-status.v1",
                "source_id": "tg-studio-main",
                "command_id": str(message.gateway_command_id),
                "external_chat_id": "chat-1",
                "external_message_id": "provider-ai-1",
                "status": "provider_accepted",
                "occurred_at": "2026-09-20T12:34:56Z",
                "failure_kind": None,
            },
            format="json",
            HTTP_AUTHORIZATION="Bearer gateway-secret",
        )
        self.assertEqual(response.status_code, 202)
        message.refresh_from_db()
        self.assertEqual(message.author_type, MessageAuthor.AI)
        self.assertEqual(message.delivery_status, "provider_accepted")
        self.assertEqual(message.external_id, "provider-ai-1")
