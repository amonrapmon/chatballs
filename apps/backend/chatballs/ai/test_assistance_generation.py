from uuid import uuid4

from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from chatballs.ai.assistance_behavior_base import AssistanceBehaviorData
from chatballs.ai.assistance_generation import begin
from chatballs.ai.assistance_history import history_snapshot
from chatballs.ai.assistance_models import ReplyAssistanceError
from chatballs.ai.models import LlmInvocation
from chatballs.ai.turn import plan_chat
from chatballs.conversations.comment_models import ConversationComment
from chatballs.conversations.models import Message
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.integrations.models import IntegrationProvider
from chatballs.tenancy.database import tenant_atomic


class AssistanceGenerationTests(AssistanceBehaviorData, TestCase):
    def dispatch_as_runtime(self, event):
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
        try:
            dispatch(event)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE NONE")

    def test_real_outbox_generation_restores_values_and_has_no_conversation_side_effects(self):
        before = list(Message.objects.values_list("pk", flat=True))
        fields = ("control_mode", "assigned_operator_id", "expected_responder", "last_activity_at")
        state = [getattr(self.conversation, field) for field in fields]
        suggestion = self.request()
        event = OutboxEvent.objects.get(event_type="conversation.reply_assistance_requested")
        self.dispatch_as_runtime(event)
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.status, "READY")
        self.assertIn("help@example.test", suggestion.original_text)
        self.assertNotIn("[[", suggestion.original_text)
        self.assertNotIn("<<HANDOFF>>", suggestion.original_text)
        self.assertEqual(list(Message.objects.values_list("pk", flat=True)), before)
        self.conversation.refresh_from_db()
        self.assertEqual([getattr(self.conversation, field) for field in fields], state)
        invocations = LlmInvocation.objects.count()
        self.dispatch_as_runtime(event)
        self.assertEqual(LlmInvocation.objects.count(), invocations)

    def test_latest_public_history_is_frozen_at_start_and_masked_with_instructions(self):
        suggestion = self.request()
        self.agent.history_limit = 2
        self.agent.instructions += " Use support@example.test."
        self.agent.save()
        latest = Message.objects.create(conversation=self.conversation, author_type="CONTACT",
                                        text="Delivery to contact@example.test?")
        from chatballs.conversations.system_events import OPERATOR_ONLY_EVENTS

        Message.objects.create(conversation=self.conversation, author_type="SYSTEM",
                               system_event=next(iter(OPERATOR_ONLY_EVENTS)), text="Secret internal handoff")
        ConversationComment.objects.create(
            conversation=self.conversation, author=self.member.user, text="Secret comment",
            audience="INTERNAL", operation_id=uuid4(),
        )
        with tenant_atomic(self.worker_context):
            work = begin(self.worker_context, suggestion.public_id)
            suggestion, conversation, history, query, mask, _ = work
            self.assertEqual(history[-1]["content"], latest.text)
            self.assertEqual(len(history), 2)
            self.assertNotIn("Secret", str(history))
            self.assertEqual(query, latest.text)
            self.assertEqual(suggestion.history_version,
                             history_snapshot(conversation, 2)[2])
            plan = plan_chat(agent=self.agent, message=query, history=history,
                             conversation=conversation, pseudonymizer=mask)
            prompt = str(plan.job.messages)
            self.assertNotIn("contact@example.test", prompt)
            self.assertNotIn("support@example.test", prompt)
            self.assertIn("[[", prompt)
            self.assertIn("attached knowledge", prompt)
            self.assertIn("Delivery", prompt)
        self.generate(suggestion)
        self.assertEqual(suggestion.status, "ERROR")
        self.assertEqual(suggestion.error_code, ReplyAssistanceError.GENERATION_FAILED)
        self.assertFalse(LlmInvocation.objects.exists())

    def test_provider_missing_is_safe_terminal_error(self):
        self.agent.provider_integration = None
        self.agent.save()
        suggestion = self.generate(self.request())
        self.assertEqual(suggestion.status, "ERROR")
        self.assertEqual(suggestion.error_code, "PROVIDER_UNAVAILABLE")
        self.assertEqual(suggestion.original_text, "")
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, "HUMAN")
        self.assertEqual(self.conversation.assigned_operator_id, self.member.user_id)
        self.assertEqual(Message.objects.count(), 1)

    def test_real_provider_connection_failure_is_safe_and_does_not_repeat_generation(self):
        integration = self.agent.provider_integration
        integration.provider = IntegrationProvider.CUSTOM
        integration.config = {"base_url": "http://127.0.0.1:1", "default_model": "test-model"}
        integration.save()
        suggestion = self.request()
        with override_settings(CHATBALLS_AI_MAX_RETRIES=0, CHATBALLS_AI_TURN_TIMEOUT=1):
            self.generate(suggestion)
        self.assertEqual(suggestion.status, "ERROR")
        self.assertEqual(suggestion.original_text, "")
        self.assertEqual(suggestion.error_code, "GENERATION_FAILED")
        invocation = LlmInvocation.objects.get(operation="chat")
        self.assertEqual(invocation.error, "GENERATION_FAILED")
        self.assertEqual(invocation.status, "ERROR")
        self.generate(suggestion)
        self.assertEqual(LlmInvocation.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 1)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, "HUMAN")
        self.assertEqual(self.conversation.assigned_operator_id, self.member.user_id)

    def test_deadline_and_revoked_requester_do_not_call_model(self):
        suggestion = self.request()
        with override_settings(CHATBALLS_AI_TURN_DEADLINE_SECONDS=-1):
            self.generate(suggestion)
        self.assertEqual(suggestion.error_code, "TIMEOUT")
        other = self.request("second")
        self.member.blocked_at = timezone.now()
        self.member.save(update_fields=["blocked_at"])
        self.generate(other)
        self.assertEqual(other.error_code, "PERMISSION_DENIED")
        self.assertEqual(Message.objects.count(), 1)
        self.assertFalse(LlmInvocation.objects.exists())
