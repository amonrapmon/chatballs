"""Transactional concurrency, incoming scheduling gaps and publication claims."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import mock

from django.db import close_old_connections, connections
from django.test import TransactionTestCase

from chatballs.ai.provider.base import ChatResult
from chatballs.ai.turn import TurnAnswer
from chatballs.conversations.ai_turn import AI_TURN_REQUESTED, run_requested_turn
from chatballs.conversations.models import AiTurnState, ControlMode, Message, MessageAuthor
from chatballs.events.models import OutboxEvent
from chatballs.native_mirror.contracts import MirrorOutcome
from chatballs.native_mirror.models import NativeMirrorConversationState, NativeMirrorReceipt
from chatballs.native_mirror.supersession_fixture import NativeMirrorTurnFixture
from chatballs.tenancy.database import tenant_atomic


class NativeMirrorSupersessionRaceTests(NativeMirrorTurnFixture, TransactionTestCase):
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
    def test_native_reply_between_inbound_persist_and_ai_scheduling(self):
        from chatballs.conversations.ai_turn import request_ai_turn

        def native_before_scheduling(**kwargs):
            self.assertEqual(self._mirror().outcome, MirrorOutcome.STORED)
            return request_ai_turn(**kwargs)

        with mock.patch(
            "chatballs.conversations.ingest.request_ai_turn",
            side_effect=native_before_scheduling,
        ):
            second = self._inbound("client-2")
        second.refresh_from_db()
        self.assertEqual(second.ai_turn_state, AiTurnState.DONE)
        self.assertFalse(OutboxEvent.objects.filter(
            event_type=AI_TURN_REQUESTED, payload__messageId=second.id,
        ).exists())
        self._assert_no_stale_effects()

