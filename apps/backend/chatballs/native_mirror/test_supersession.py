"""Native mirror supersession at scheduling, planning and finalization.

Real PostgreSQL transactions verify that a trusted native reply wins against
old PENDING/RUNNING work without flipping AI to HUMAN. Gateway send is never
queued for a superseded result.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from unittest import mock

from django.db import close_old_connections, connections
from django.test import TransactionTestCase

from chatballs.ai.models import AIAgent, AIAgentStatus
from chatballs.ai.provider.base import ProviderError
from chatballs.channels.models import Channel
from chatballs.conversations.ai_turn import (
    AI_TURN_REQUESTED, _apply_transcript, _begin, conversation_is_thinking,
    run_requested_turn,
)
from chatballs.conversations.ai_turn_completion import (
    _commit_if_current, finish_planning_failure,
)
from chatballs.conversations.ai_turn_result import store_answer
from chatballs.conversations.gateway_delivery import GATEWAY_DELIVERY_COMMAND_REQUESTED
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import (
    AiTurnState, ControlMode, Message, MessageAuthor, SystemEvent,
)
from chatballs.conversations.transports.base import InboundMessage
from chatballs.events.models import OutboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.native_mirror.classification import OriginClass
from chatballs.native_mirror.contracts import MirrorOutcome, NativeReplyEvent
from chatballs.native_mirror.models import NativeMirrorConversationState, NativeMirrorReceipt
from chatballs.native_mirror.service import accept_native_reply
from chatballs.testing import system_tenant_context
from chatballs.tenancy.database import tenant_atomic


class NativeMirrorSupersessionTests(TransactionTestCase):
    def setUp(self):
        result = bootstrap_owner(
            email="mirror-supersede@example.com", password="temporary-password"
        )
        self.organization = result.organization
        self.owner = result.owner
        self.context = system_tenant_context(self.organization)
        self.channel = Channel.objects.create(
            organization=self.organization, code="mirror-supersede", name="Mirror AI"
        )
        self.agent = AIAgent.objects.create(
            channel=self.channel, name="AI", model="openai/gpt-4o-mini",
            status=AIAgentStatus.ACTIVE,
        )
        self.integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.GATEWAY,
            channel=self.channel, name="Test Gateway", secret="test",
            config={
                "source_id": "tg-native", "base_url": "https://gateway.example.test/",
                "native_mirror_mode": "ENABLED",
            },
        )
        self._inbound("client-1")
        self.message = Message.objects.get(
            author_type=MessageAuthor.CONTACT, external_id="client-1",
        )
        self.conversation = self.message.conversation

    def _inbound(self, external_id):
        ingest_inbound(
            self.integration,
            InboundMessage(
                external_id=external_id, user_id="visitor-1", chat_id="chat-1",
                text="Можно записаться?", display_name="Visitor",
            ),
        )
        return Message.objects.get(
            author_type=MessageAuthor.CONTACT, external_id=external_id,
        )

    def _payload(self, message=None):
        message = message or self.message
        return OutboxEvent.objects.get(
            event_type=AI_TURN_REQUESTED, payload__messageId=message.id,
        ).payload

    def _mirror(self, suffix="1"):
        return accept_native_reply(
            event=NativeReplyEvent(
                integration_id=self.integration.id,
                provider=IntegrationProvider.GATEWAY,
                source_id="tg-native",
                external_chat_id="chat-1",
                event_id=f"native-event-{suffix}",
                external_message_id=f"native-msg-{suffix}",
                occurred_at=datetime(2026, 10, 12, tzinfo=UTC),
                text="Ответила в Telegram",
            ),
            context=self.context, origin=OriginClass.EXTERNAL_AUTHORIZED,
            author_user_id=self.owner.id,
        )

    def _start(self, message=None, revision=None):
        message = message or self.message
        if revision is None:
            revision = self._payload(message)["mirrorRevision"]
        with tenant_atomic(self.context):
            return _begin(
                message_id=message.id, user_id="visitor-1", is_new=False,
                context=self.context, mirror_revision=revision,
            )

    def _finish(self, turn, text="Старый ответ AI"):
        return _commit_if_current(
            turn=turn, context=self.context,
            persist=lambda: store_answer(
                turn=turn, context=self.context, text=text,
            ),
        )

    def _assert_no_stale_effects(self):
        self.assertFalse(Message.objects.filter(author_type=MessageAuthor.AI).exists())
        self.assertFalse(OutboxEvent.objects.filter(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
        ).exists())
        self.assertFalse(Message.objects.filter(
            system_event__in=(SystemEvent.AI_UNAVAILABLE, SystemEvent.AI_HANDED_OVER),
        ).exists())

    def test_pending_snapshot_captured_before_native_reply_is_superseded(self):
        payload = self._payload()
        self.assertEqual(payload["mirrorRevision"], 0)
        self.assertEqual(self._mirror().outcome, MirrorOutcome.STORED)
        self.message.refresh_from_db()
        self.assertEqual(self.message.ai_turn_state, AiTurnState.DONE)
        self.assertFalse(conversation_is_thinking(self.conversation.id))
        with mock.patch("chatballs.conversations.ai_turn.run_turn_chat") as model:
            run_requested_turn(payload, self.context)
        model.assert_not_called()
        self._assert_no_stale_effects()

    def test_running_result_is_rejected_after_operator_mirror(self):
        turn = self._start()
        self.assertIsNotNone(turn)
        self.assertEqual(self._mirror().outcome, MirrorOutcome.STORED)
        self.assertIsNone(self._finish(turn))
        self.message.refresh_from_db()
        self.assertEqual(self.message.ai_turn_state, AiTurnState.DONE)
        self.assertFalse(conversation_is_thinking(self.conversation.id))
        self._assert_no_stale_effects()
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, ControlMode.AI)

    def test_planning_failure_after_supersede_has_no_fallback_or_handoff(self):
        turn = self._start()
        self._mirror()
        self.assertIsNone(finish_planning_failure(
            turn=turn, context=self.context, error=ProviderError("too late"),
        ))
        self._assert_no_stale_effects()

    def test_late_transcription_after_supersede_is_ignored(self):
        turn = self._start()
        self._mirror()
        with tenant_atomic(self.context):
            self.assertFalse(_apply_transcript(
                turn=turn, transcript="Поздняя стенограмма", context=self.context
            ))
        self.message.refresh_from_db()
        self.assertFalse(self.message.transcript)
        self._assert_no_stale_effects()

    def test_next_customer_turn_after_native_reply_uses_new_revision(self):
        self._mirror()
        second = self._inbound("client-2")
        payload = self._payload(second)
        self.assertEqual(payload["mirrorRevision"], 1)
        turn = self._start(second)
        self.assertIsNotNone(turn)
        self.assertEqual(self._finish(turn, text="Новый ответ"), "Новый ответ")
        self.assertEqual(Message.objects.filter(
            author_type=MessageAuthor.AI, text="Новый ответ",
        ).count(), 1)
        self.assertEqual(NativeMirrorConversationState.objects.get().revision, 1)

    def test_duplicate_native_event_does_not_supersede_a_new_turn(self):
        self._mirror()
        second = self._inbound("client-2")
        turn = self._start(second)
        self.assertIsNotNone(turn)
        self.assertEqual(self._mirror().outcome, MirrorOutcome.DUPLICATE)
        self.assertEqual(self._finish(turn), "Старый ответ AI")
        self.assertEqual(NativeMirrorConversationState.objects.get().revision, 1)

    def test_older_epoch_is_rejected_even_when_turn_state_is_pending(self):
        self._mirror()
        second = self._inbound("client-2")
        with tenant_atomic(self.context):
            old = _begin(
                message_id=second.id, user_id="visitor-1", is_new=False,
                context=self.context, mirror_revision=0,
            )
        self.assertIsNone(old)
        second.refresh_from_db()
        self.assertEqual(second.ai_turn_state, AiTurnState.DONE)
        self._assert_no_stale_effects()

    def test_known_echo_and_unclassified_events_do_not_interrupt_ai(self):
        turn = self._start()
        for origin, suffix in (
            (OriginClass.EXTERNAL_UNCLASSIFIED, "unclassified"),
            (OriginClass.SELF_ECHO, "unknown-echo"),
        ):
            result = accept_native_reply(
                event=NativeReplyEvent(
                    integration_id=self.integration.id,
                    provider=IntegrationProvider.GATEWAY,
                    source_id="tg-native",
                    external_chat_id="chat-1", event_id=suffix,
                    external_message_id=suffix,
                    occurred_at=datetime(2026, 10, 12, tzinfo=UTC),
                    text="ignored",
                ), context=self.context, origin=origin,
            )
            self.assertEqual(result.outcome, MirrorOutcome.UNCLASSIFIED)
        self.assertEqual(self._finish(turn), "Старый ответ AI")
        self.assertFalse(NativeMirrorConversationState.objects.exists())

    def test_native_transaction_rollback_restores_running_turn(self):
        turn = self._start()
        original = NativeMirrorReceipt.save

        def fail_stored(instance, *args, **kwargs):
            if instance.status == "STORED":
                raise RuntimeError("receipt save failed")
            return original(instance, *args, **kwargs)

        with (
            mock.patch.object(NativeMirrorReceipt, "save", fail_stored),
            self.assertRaises(RuntimeError),
        ):
            self._mirror()
        self.message.refresh_from_db()
        self.assertEqual(self.message.ai_turn_state, AiTurnState.RUNNING)
        self.assertEqual(self._finish(turn), "Старый ответ AI")
        self.assertFalse(NativeMirrorReceipt.objects.exists())

    def test_operator_mirror_lock_wins_against_remote_finalizer(self):
        turn = self._start()
        barrier = Barrier(2)

        def finish_in_thread():
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return self._finish(turn)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with tenant_atomic(self.context):
                locked = self.conversation.__class__.objects.select_for_update().get(
                    id=self.conversation.id,
                )
                self.assertEqual(locked.control_mode, ControlMode.AI)
                future = executor.submit(finish_in_thread)
                barrier.wait(timeout=15)
                self.assertEqual(self._mirror().outcome, MirrorOutcome.STORED)
            self.assertIsNone(future.result(timeout=30))
        self._assert_no_stale_effects()

    def test_model_returns_after_native_reply_without_publishing(self):
        from chatballs.ai.provider.base import ChatResult
        from chatballs.ai.turn import TurnAnswer

        def answer(*_args, **_kwargs):
            self._mirror()
            return TurnAnswer(result=ChatResult(
                text="Too late", model="test", prompt_tokens=1, completion_tokens=1,
            ))

        with mock.patch("chatballs.conversations.ai_turn.run_turn_chat", side_effect=answer):
            run_requested_turn(self._payload(), self.context)
        self._assert_no_stale_effects()

    def test_committed_publication_is_not_claimed_revocable(self):
        turn = self._start()
        self.assertEqual(self._finish(turn), "Старый ответ AI")
        self.assertEqual(self._mirror().outcome, MirrorOutcome.STORED)
        self.assertEqual(Message.objects.filter(author_type=MessageAuthor.AI).count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
        ).count(), 1)
        self.assertEqual(NativeMirrorConversationState.objects.get().revision, 1)
