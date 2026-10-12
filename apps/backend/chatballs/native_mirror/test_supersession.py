"""Trusted external operator reply supersedes older queued and running AI turns."""

from datetime import UTC, datetime
from unittest import mock

from django.test import TransactionTestCase

from chatballs.ai.provider.base import ProviderError
from chatballs.conversations.ai_turn import (
    _apply_transcript, _begin, conversation_is_thinking, run_requested_turn,
)
from chatballs.conversations.ai_turn_completion import finish_planning_failure
from chatballs.conversations.models import AiTurnState, ControlMode, Message, MessageAuthor
from chatballs.integrations.models import IntegrationProvider
from chatballs.native_mirror.classification import OriginClass
from chatballs.native_mirror.contracts import MirrorOutcome, NativeReplyEvent
from chatballs.native_mirror.models import NativeMirrorConversationState
from chatballs.native_mirror.service import accept_native_reply
from chatballs.native_mirror.supersession_fixture import NativeMirrorTurnFixture
from chatballs.tenancy.database import tenant_atomic


class NativeMirrorSupersessionTests(NativeMirrorTurnFixture, TransactionTestCase):
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

