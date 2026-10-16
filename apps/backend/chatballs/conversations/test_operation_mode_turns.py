"""Significant ingress and cancellation behavior, using the existing turn pipeline."""

from unittest.mock import patch

from django.test import TestCase

from chatballs.ai.models import AIAgent
from chatballs.channels.models import Channel
from chatballs.conversations.ai_reply_delivery import deliver_saved
from chatballs.conversations.ai_turn import _begin, conversation_is_thinking
from chatballs.conversations.ai_turn_completion import refresh_turn_control
from chatballs.conversations.control_services import ClaimError, claim_conversation, release_to_ai
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import Message
from chatballs.conversations.transports.base import InboundMessage
from chatballs.identity.models import HumanUser, Organization, OrganizationMembership
from chatballs.identity.operation_modes import change_operation_mode, lock_organization
from chatballs.integrations.models import Integration
from chatballs.testing import ai_answer, run_pending_ai_turns, tenant_context_for


class OperationModeTurnTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Org", slug="turn-mode")
        user = HumanUser.objects.create_user(email="owner@turn-mode.test")
        OrganizationMembership.objects.create(organization=self.organization, user=user, role="OWNER")
        self.context = tenant_context_for(user)
        self.channel = Channel.objects.create(organization=self.organization, code="line", name="Line")
        provider = Integration.objects.create(organization=self.organization, name="Demo", kind="LLM_PROVIDER",
                                              provider="DEMO", secret="demo")
        self.agent = AIAgent.objects.create(channel=self.channel, name="Agent", status="ACTIVE",
                                            provider_integration=provider, model="demo")
        self.connection = Integration.objects.create(organization=self.organization, name="Web", kind="MESSENGER",
                                                    provider="WEB", channel=self.channel)
        self.inbound = InboundMessage(external_id="1", chat_id="chat", user_id="customer", text="Hello", display_name="Customer")

    def switch(self, mode):
        change_operation_mode(context=self.context, organization=lock_organization(self.organization.pk), mode=mode)

    def incoming(self):
        ingest_inbound(self.connection, self.inbound)
        return Message.objects.get(author_type="CONTACT")

    def test_all_supported_ingress_queues_without_autonomous_work(self):
        self.switch("OPERATORS_ONLY")
        with patch("chatballs.conversations.ai_turn.request_ai_turn") as request, patch("chatballs.ai.turn.plan_chat") as plan:
            for index, provider in enumerate(["TELEGRAM", "MAX", "VK", "WEB", "EMAIL"]):
                with self.subTest(provider=provider):
                    connection = Integration.objects.create(organization=self.organization, name=provider, kind="MESSENGER",
                                                            provider=provider, channel=self.channel)
                    inbound = InboundMessage(external_id=str(index), user_id=f"customer-{index}", chat_id="chat", text="Hi", display_name="Customer")
                    ingest_inbound(connection, inbound)
                    conversation = self.channel.conversations.get(connection=connection)
                    self.assertEqual(conversation.control_mode, "PAUSED")
                    self.assertIsNotNone(conversation.waiting_since)
                    self.assertEqual(conversation.expected_responder, "OPERATOR")
                    self.assertFalse(conversation_is_thinking(conversation.pk))
            request.assert_not_called()
            plan.assert_not_called()
        self.assertFalse(Message.objects.filter(author_type="AI").exists())

    def test_pending_turn_is_not_resurrected_by_fast_off_on(self):
        source = self.incoming()
        self.switch("OPERATORS_ONLY")
        self.switch("AI_AGENTS")
        with ai_answer("stale") as chat:
            run_pending_ai_turns()
        chat.assert_not_called()
        self.assertFalse(Message.objects.filter(author_type="AI").exists())
        self.assertFalse(conversation_is_thinking(source.conversation_id))

    def test_completion_during_switch_cannot_store_a_stale_answer(self):
        source = self.incoming()
        def finish(*args, **kwargs):
            self.switch("OPERATORS_ONLY")
            self.switch("AI_AGENTS")
            from chatballs.ai.provider.base import ChatResult
            from chatballs.ai.turn_types import TurnAnswer
            return TurnAnswer(result=ChatResult(text="stale", model="demo", prompt_tokens=1, completion_tokens=1))
        with patch("chatballs.conversations.ai_turn.run_turn_chat", side_effect=finish):
            run_pending_ai_turns()
        self.assertFalse(Message.objects.filter(author_type="AI").exists())
        source.refresh_from_db()
        self.assertEqual(source.ai_turn_state, "DONE")

    def test_saved_reply_and_retry_reject_old_mode_generation(self):
        source = self.incoming()
        with ai_answer("saved"), patch("chatballs.conversations.ai_turn._deliver"):
            run_pending_ai_turns()
        self.assertTrue(Message.objects.filter(ai_reply_to=source).exists())
        self.switch("OPERATORS_ONLY")
        self.switch("AI_AGENTS")
        with patch("chatballs.conversations.transports.send_reply") as send:
            deliver_saved(source.pk, self.context)
            deliver_saved(source.pk, self.context)
        send.assert_not_called()

    def test_claim_cancels_running_turn_and_pending_delivery_even_after_release(self):
        source = self.incoming()
        turn = _begin(message_id=source.pk, user_id="customer", is_new=True, context=self.context)
        self.assertIsNotNone(turn)
        claim_conversation(context=self.context, conversation_id=source.conversation_id)
        release_to_ai(context=self.context, conversation_id=source.conversation_id)
        self.assertFalse(refresh_turn_control(turn, self.context))
        self.assertFalse(conversation_is_thinking(source.conversation_id))

    def test_return_to_ai_is_rejected_without_mutation(self):
        source = self.incoming()
        claim_conversation(context=self.context, conversation_id=source.conversation_id)
        self.switch("OPERATORS_ONLY")
        with self.assertRaises(ClaimError):
            release_to_ai(context=self.context, conversation_id=source.conversation_id)
        source.conversation.refresh_from_db()
        self.assertEqual(source.conversation.control_mode, "HUMAN")

    def test_missing_agent_is_normal_queue_in_ai_mode(self):
        self.agent.delete()
        self.channel.refresh_from_db()
        source = self.incoming()
        self.assertEqual(source.conversation.control_mode, "PAUSED")
        self.assertEqual(source.ai_turn_state, "NONE")
        self.assertFalse(Message.objects.filter(author_type="AI").exists())

    def test_new_dialog_can_answer_after_reenabling(self):
        self.switch("OPERATORS_ONLY")
        self.switch("AI_AGENTS")
        self.incoming()
        with ai_answer("Hello"):
            run_pending_ai_turns()
        reply = Message.objects.get(author_type="AI")
        self.assertTrue(reply.ai_delivery["sent"])

    def test_direct_server_entry_cannot_bypass_operator_mode(self):
        from chatballs.ai.provider.base import ProviderError
        from chatballs.channels.runtime import run_channel_turn

        self.switch("OPERATORS_ONLY")
        with patch("chatballs.channels.runtime.run_agent_turn") as run:
            with self.assertRaises(ProviderError):
                run_channel_turn(channel=self.channel, message="Hello")
        run.assert_not_called()

    def test_mode_does_not_enable_assistance_or_replace_explicit_providers(self):
        provider_id = self.agent.provider_integration_id
        self.switch("OPERATORS_ONLY")
        self.switch("AI_AGENTS")
        self.agent.refresh_from_db()
        self.assertFalse(self.agent.assistance_enabled)
        self.assertEqual(self.agent.provider_integration_id, provider_id)
        self.assertIsNone(self.agent.transcription_integration_id)
