"""PostgreSQL races at the AI-turn persistence boundary.

TransactionTestCase is required: TestCase wraps setup data in an uncommitted
transaction that a second PostgreSQL connection cannot see.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import mock

from django.db import close_old_connections, connections
from django.test import TransactionTestCase

from chatballs.ai.models import AIAgent, AIAgentStatus
from chatballs.ai.provider.base import ProviderError
from chatballs.ai.runtime import HANDOFF_TOKEN
from chatballs.channels.models import Channel
from chatballs.conversations.ai_turn import _apply_transcript, _begin, conversation_is_thinking
from chatballs.conversations.ai_turn_completion import (
    _commit_if_current,
    finish_planning_failure,
)
from chatballs.conversations.ai_turn_result import store_answer
from chatballs.conversations.gateway_delivery import GATEWAY_DELIVERY_COMMAND_REQUESTED
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import (
    AiTurnState,
    ControlMode,
    LifecycleState,
    Message,
    MessageAuthor,
    SystemEvent,
)
from chatballs.conversations.transports.base import InboundMessage
from chatballs.events.models import OutboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.testing import system_tenant_context
from chatballs.tenancy.database import tenant_atomic


class AiTurnConcurrentFinalizationTests(TransactionTestCase):
    def setUp(self):
        bootstrap_owner(email="turn-race@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.context = system_tenant_context(self.organization)
        self.channel = Channel.objects.create(
            organization=self.organization, code="turn-race", name="AI turn race"
        )
        self.agent = AIAgent.objects.create(
            channel=self.channel, name="Agent",
            model="openai/gpt-4o-mini", status=AIAgentStatus.ACTIVE,
        )
        self.integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.GATEWAY,
            name="Test Gateway",
            secret="test-secret",
            config={"source_id": "tg-test", "base_url": "https://gateway.example.test/"},
            channel=self.channel,
        )
        ingest_inbound(self.integration, InboundMessage(
            external_id="inbound-1", user_id="user-1", chat_id="chat-1",
            text="Здравствуйте", display_name="Гость",
        ))
        self.message = Message.objects.get(author_type=MessageAuthor.CONTACT)
        self.conversation = self.message.conversation

    def _begin_turn(self):
        with tenant_atomic(self.context):
            turn = _begin(
                message_id=self.message.id, user_id="user-1",
                is_new=False, context=self.context,
            )
        self.assertIsNotNone(turn)
        return turn

    def _finish(self, turn, text="Ответ AI"):
        return _commit_if_current(
            turn=turn,
            context=self.context,
            persist=lambda: store_answer(turn=turn, context=self.context, text=text),
        )

    def _assert_no_reply(self):
        self.assertFalse(Message.objects.filter(author_type=MessageAuthor.AI).exists())
        self.assertFalse(OutboxEvent.objects.filter(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED
        ).exists())

    def test_two_concurrent_workers_commit_one_ai_message_and_one_gateway_command(self):
        first = self._begin_turn()
        second = self._begin_turn()  # RUNNING is deliberately reclaimable.
        barrier = Barrier(3)

        def worker(turn):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return self._finish(turn)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            left = executor.submit(worker, first)
            right = executor.submit(worker, second)
            barrier.wait(timeout=15)
            outcomes = (left.result(timeout=30), right.result(timeout=30))

        self.assertCountEqual(outcomes, ["Ответ AI", None])
        self.assertEqual(Message.objects.filter(author_type=MessageAuthor.AI).count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED
        ).count(), 1)
        self.message.refresh_from_db()
        self.assertEqual(self.message.ai_turn_state, AiTurnState.DONE)
        self.assertFalse(conversation_is_thinking(self.conversation.id))


    def test_parallel_full_turn_uses_one_publication_after_two_model_responses(self):
        from chatballs.ai.provider.base import ChatResult
        from chatballs.ai.turn import TurnAnswer
        from chatballs.conversations.ai_turn import run_requested_turn

        barrier = Barrier(3)
        payload = {"messageId": self.message.id, "userId": "user-1"}

        def answer(*args, **kwargs):
            barrier.wait(timeout=20)
            return TurnAnswer(result=ChatResult(
                text="Единственный ответ", model="test",
                prompt_tokens=1, completion_tokens=1,
            ))

        def worker():
            close_old_connections()
            try:
                run_requested_turn(payload, self.context)
            finally:
                connections.close_all()

        with mock.patch("chatballs.conversations.ai_turn.run_turn_chat", side_effect=answer):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(worker) for _ in range(2)]
                barrier.wait(timeout=20)
                for future in futures:
                    future.result(timeout=30)

        self.assertEqual(Message.objects.filter(author_type=MessageAuthor.AI).count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED
        ).count(), 1)
        self.message.refresh_from_db()
        self.assertEqual(self.message.ai_turn_state, AiTurnState.DONE)

    def test_human_takeover_rejects_stale_result_and_clears_typing(self):
        turn = self._begin_turn()
        self.conversation.control_mode = ControlMode.HUMAN
        self.conversation.save(update_fields=["control_mode"])
        self.assertIsNone(self._finish(turn))
        self._assert_no_reply()
        self.message.refresh_from_db()
        self.assertEqual(self.message.ai_turn_state, AiTurnState.DONE)
        self.assertFalse(conversation_is_thinking(self.conversation.id))

    def test_paused_conversation_rejects_planning_failure_without_handoff(self):
        turn = self._begin_turn()
        self.conversation.control_mode = ControlMode.PAUSED
        self.conversation.save(update_fields=["control_mode"])
        outcome = finish_planning_failure(
            turn=turn, context=self.context, error=ProviderError("provider down"),
        )
        self.assertIsNone(outcome)
        self._assert_no_reply()
        self.assertFalse(Message.objects.filter(system_event=SystemEvent.AI_UNAVAILABLE).exists())
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, ControlMode.PAUSED)
        self.message.refresh_from_db()
        self.assertEqual(self.message.ai_turn_state, AiTurnState.DONE)

    def test_closed_conversation_rejects_completion(self):
        turn = self._begin_turn()
        self.conversation.lifecycle = LifecycleState.CLOSED
        self.conversation.save(update_fields=["lifecycle"])
        self.assertIsNone(self._finish(turn))
        self._assert_no_reply()

    def test_disabled_agent_rejects_completion(self):
        turn = self._begin_turn()
        self.agent.status = AIAgentStatus.DISABLED
        self.agent.save(update_fields=["status"])
        self.assertIsNone(self._finish(turn))
        self._assert_no_reply()

    def test_handoff_has_only_one_system_event_and_no_empty_gateway_command(self):
        first, duplicate = self._begin_turn(), self._begin_turn()
        self.assertEqual(self._finish(first, text=HANDOFF_TOKEN), "")
        self.assertIsNone(self._finish(duplicate, text=HANDOFF_TOKEN))
        self.assertEqual(Message.objects.filter(
            system_event=SystemEvent.AI_HANDED_OVER
        ).count(), 1)
        self.assertFalse(OutboxEvent.objects.filter(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED
        ).exists())

    def test_gateway_outbox_error_rolls_back_and_turn_can_retry(self):
        turn = self._begin_turn()
        with (
            mock.patch(
                "chatballs.conversations.gateway_delivery.enqueue_event",
                side_effect=RuntimeError("outbox unavailable"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self._finish(turn)
        self._assert_no_reply()
        self.message.refresh_from_db()
        self.assertEqual(self.message.ai_turn_state, AiTurnState.RUNNING)
        self.assertEqual(self._finish(turn), "Ответ AI")
        self.assertEqual(OutboxEvent.objects.filter(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED
        ).count(), 1)


    def test_failure_wins_against_late_success_without_duplicate_notifications(self):
        first, late = self._begin_turn(), self._begin_turn()
        fallback = finish_planning_failure(
            turn=first, context=self.context, error=ProviderError("down"),
        )
        self.assertTrue(fallback)
        self.assertIsNone(self._finish(late))
        self.assertEqual(Message.objects.filter(author_type=MessageAuthor.AI).count(), 1)
        self.assertEqual(Message.objects.filter(
            system_event=SystemEvent.AI_UNAVAILABLE
        ).count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED
        ).count(), 1)
        self.message.refresh_from_db()
        self.assertEqual(self.message.ai_turn_state, AiTurnState.FAILED)

    def test_other_tenant_cannot_claim_turn(self):
        turn = self._begin_turn()
        other = Organization.objects.create(slug="other-tenant", name="Other tenant")
        wrong_context = system_tenant_context(other)
        invoked = []
        outcome = _commit_if_current(
            turn=turn, context=wrong_context,
            persist=lambda: invoked.append("written") or "wrong",
        )
        self.assertIsNone(outcome)
        self.assertEqual(invoked, [])
        self._assert_no_reply()
        self.message.refresh_from_db()
        self.assertEqual(self.message.ai_turn_state, AiTurnState.RUNNING)

    def test_takeover_lock_beats_late_finalizer_in_another_connection(self):
        turn = self._begin_turn()
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return self._finish(turn)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with tenant_atomic(self.context):
                conversation = self.conversation.__class__.objects.select_for_update().get(
                    id=self.conversation.id,
                )
                future = executor.submit(worker)
                barrier.wait(timeout=15)
                conversation.control_mode = ControlMode.HUMAN
                conversation.save(update_fields=["control_mode"])
            self.assertIsNone(future.result(timeout=30))

        self._assert_no_reply()
        self.message.refresh_from_db()
        self.assertEqual(self.message.ai_turn_state, AiTurnState.DONE)

    def test_transcription_arriving_after_takeover_is_ignored(self):
        turn = self._begin_turn()
        self.conversation.control_mode = ControlMode.HUMAN
        self.conversation.save(update_fields=["control_mode"])
        with tenant_atomic(self.context):
            self.assertFalse(_apply_transcript(
                turn=turn, transcript="Поздний текст", context=self.context
            ))
        self.message.refresh_from_db()
        self.assertFalse(self.message.transcript)
        self.assertEqual(self.message.ai_turn_state, AiTurnState.DONE)
        self._assert_no_reply()
