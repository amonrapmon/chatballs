import json
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase, override_settings

from chatballs.ai.diagnostic_models import TurnDiagnostic
from chatballs.ai.models import AgentTool, LlmInvocation
from chatballs.ai.provider.base import ProviderRejected
from chatballs.ai.provider.demo import DemoProvider
from chatballs.ai.skill_runtime_testing import SkillRuntimeSetup
from chatballs.ai.tool_loop_testing import ScriptedProvider, calls, says
from chatballs.ai.tool_support import resolve_tool_support
from chatballs.ai.turn_skills import LOAD_SKILL
from chatballs.conversations.ai_turn import run_requested_turn
from chatballs.conversations.models import (
    AiTurnState,
    Contact,
    ControlMode,
    Conversation,
    Message,
    MessageAuthor,
)
from chatballs.events.models import OutboxEvent
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.integrations.tool_client import ToolResponse
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import system_tenant_context


@override_settings(CHATBALLS_AI_PROVIDER="", CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class SkillChatTests(SkillRuntimeSetup, TransactionTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        integration = Integration.objects.create(
            organization=self.organization, name="Demo", kind=IntegrationKind.LLM_PROVIDER,
            provider=IntegrationProvider.DEMO, secret="demo", config={"default_model": "demo"},
        )
        self.agent.provider_integration = integration
        self.agent.save(update_fields=["provider_integration"])

    def post(self, provider, **body):
        with patch("chatballs.ai.invocation.get_provider", return_value=provider):
            return self.client.post(self.chat_url, {"message": "Помогите с обращением", **body}, format="json")

    def load(self):
        return calls((LOAD_SKILL, {"skill_id": str(self.skill.public_id)}))

    def conversation(self):
        contact = Contact.objects.create(organization=self.organization, name="Анна", email="anna@example.test")
        web = Integration.objects.create(organization=self.organization, channel=self.agent.channel,
                                        name="Web", kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.WEB)
        return Conversation.objects.create(organization=self.organization, channel=self.agent.channel,
                                           contact=contact, connection=web)

    def live(self, provider, conversation):
        incoming = Message.objects.create(
            organization=self.organization, conversation=conversation, author_type=MessageAuthor.CONTACT,
            text="Помогите с обращением", ai_turn_state=AiTurnState.PENDING,
        )
        with (patch("chatballs.ai.invocation.get_provider", return_value=provider),
              patch("chatballs.conversations.transports.send_reply", return_value=True) as send):
            run_requested_turn({"messageId": incoming.pk, "userId": "visitor"}, system_tenant_context(self.organization))
        incoming.refresh_from_db()
        return incoming, send

    def test_clarification_without_templates_uses_runtime_role_and_stores_no_clients(self):
        self.assertTrue(resolve_tool_support(self.agent))
        provider = ScriptedProvider(self.load(), says("Уточните номер обращения."))
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE chatballs_runtime_app")
        try:
            response = self.post(provider)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["reply"], "Уточните номер обращения.")
        self.assertEqual((body["skillSupport"], body["skillWarning"], body["toolCalls"]), ("supported", "", []))
        self.assertEqual((body["promptTokens"], body["completionTokens"]), (20, 10))
        self.assertNotIn(self.skill.instruction, repr(provider.requests[0]))
        self.assertIn(self.skill.instruction, provider.tool_results()[0])
        self.assertEqual(LlmInvocation.objects.filter(operation="chat").count(), 2)
        for model in (Contact, Conversation, Message, OutboxEvent, TurnDiagnostic):
            self.assertEqual(model.objects.count(), 0, model.__name__)

    def test_unsupported_unknown_and_rejected_models_never_receive_full_text_fallback(self):
        with patch.object(DemoProvider, "supports_tools", return_value=False):
            self.assertFalse(resolve_tool_support(self.agent))
        provider = ScriptedProvider(says("Обычный ответ"))
        response = self.post(provider)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["skillSupport"], "unsupported")
        self.assertTrue(response.json()["skillWarning"])
        self.assertIsNone(provider.requests[0].tools)
        self.assertNotIn(self.skill.instruction, provider.sent())
        cache.clear()
        provider = ScriptedProvider(ProviderRejected("tools unavailable"))
        response = self.post(provider)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(provider.requests), 1)
        self.assertNotIn(self.skill.instruction, provider.sent())
        cache.clear()
        response = self.post(ScriptedProvider(says("Ответ")))
        self.assertEqual(response.json()["skillSupport"], "unknown")

    def test_live_and_test_chat_load_identical_instruction_and_mask_diagnostics(self):
        self.skill.name = "Уточнение для Анна anna@example.test"
        self.skill.description = "Когда Анна не указала номер"
        self.skill.instruction = "Спросите у Анна номер; почта anna@example.test."
        self.skill.save()
        self.agent.answer_language = "en"
        self.agent.save(update_fields=["answer_language"])
        provider = ScriptedProvider(self.load(), says("[[client_name]], please give the reference number."))
        response = self.post(provider, clientData={"name": "Анна", "email": "anna@example.test"})
        self.assertEqual(response.status_code, 200, response.content)
        test_instruction = provider.tool_results()[0]
        live_provider = ScriptedProvider(self.load(), says("[[client_name]], please give the reference number."))
        conversation = self.conversation()
        incoming, send = self.live(live_provider, conversation)
        self.assertEqual(incoming.ai_turn_state, AiTurnState.DONE)
        self.assertEqual(live_provider.tool_results()[0], test_instruction)
        self.assertEqual(send.call_args.kwargs["text"], response.json()["reply"])
        system = "\n".join(m.content for m in live_provider.requests[1].messages if m.role == "system")
        self.assertIn("English", system)
        self.assertIn("<<HANDOFF>>", system)
        self.assertIn("не даёт новых прав", system)
        payload = TurnDiagnostic.objects.get(message=incoming).payload
        stored = json.dumps(payload, ensure_ascii=False) + repr(list(LlmInvocation.objects.values()))
        sent = live_provider.sent() + repr(live_provider.requests[0].tools)
        for value in ("Анна", "anna@example.test"):
            self.assertNotIn(value, sent)
            self.assertNotIn(value, stored)
        self.assertEqual(payload["toolCalls"], [])
        self.assertEqual(len(payload["rounds"]), 2)

    def test_handoff_manual_takeover_and_agent_without_skills_keep_existing_behavior(self):
        conversation = self.conversation()
        incoming, send = self.live(ScriptedProvider(self.load(), says("Передаю специалисту.\n<<HANDOFF>>")), conversation)
        self.assertEqual(incoming.ai_turn_state, AiTurnState.DONE)
        self.assertNotIn("<<HANDOFF>>", send.call_args.kwargs["text"])
        conversation.refresh_from_db()
        self.assertNotEqual(conversation.control_mode, ControlMode.AI)
        provider = ScriptedProvider(self.load())
        _, send = self.live(provider, conversation)
        self.assertEqual(provider.requests, [])
        send.assert_not_called()
        self.agent.skill_assignments.all().delete()
        provider = ScriptedProvider(says("Обычный ответ"))
        response = self.post(provider)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(provider.requests[0].tools)
        self.assertEqual(len(provider.requests), 1)

    def test_internal_and_enabled_http_calls_share_rounds_and_only_http_has_trace(self):
        http = Integration.objects.create(
            organization=self.organization, name="Lookup", kind=IntegrationKind.EXTERNAL_SERVER,
            provider=IntegrationProvider.HTTP, config={"tool_name": "lookup", "description": "anna@example.test",
                "method": "GET", "url": "https://example.test/lookup", "parameters": []},
        )
        AgentTool.objects.create(organization=self.organization, agent=self.agent, integration=http)
        provider = ScriptedProvider(self.load(), calls(("lookup", {})), says("Ответ"))
        with patch("chatballs.integrations.http_tool.fetch", return_value=ToolResponse(
            status=200, content_type="application/json", body=b'{"status":"open"}', url="",
        )) as fetch:
            response = self.post(provider)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(provider.requests), 3)
        self.assertEqual([call["name"] for call in response.json()["toolCalls"]], ["lookup"])
        self.assertNotIn("anna@example.test", repr(provider.requests[0].tools))
        self.assertLessEqual(fetch.call_args.kwargs["timeout"], 30)
        self.assertEqual(LlmInvocation.objects.filter(operation="chat").count(), 3)

    def test_takeover_during_model_round_discards_reply_but_keeps_token_accounting(self):
        conversation = self.conversation()
        provider = ScriptedProvider(self.load(), says("Ответ AI, который уже не нужен"))
        chat = provider.chat

        def takeover(**kwargs):
            result = chat(**kwargs)
            if len(provider.requests) == 1:
                with tenant_atomic(self.context):
                    Conversation.objects.filter(pk=conversation.pk).update(control_mode=ControlMode.HUMAN)
            return result

        with patch.object(provider, "chat", side_effect=takeover):
            incoming, send = self.live(provider, conversation)
        send.assert_not_called()
        self.assertEqual(incoming.ai_turn_state, AiTurnState.DONE)
        self.assertFalse(Message.objects.filter(author_type=MessageAuthor.AI).exists())
        self.assertEqual(LlmInvocation.objects.filter(operation="chat").count(), 2)
        conversation.refresh_from_db()
        self.assertEqual(conversation.control_mode, ControlMode.HUMAN)
