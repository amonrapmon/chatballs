import json
from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from chatballs.ai.diagnostic_models import TurnDiagnostic
from chatballs.ai.models import LlmInvocation
from chatballs.ai.provider.base import ProviderError
from chatballs.ai.skill_runtime_testing import SkillRuntimeSetup
from chatballs.ai.template_runtime_testing import TEMPLATE_ID, SelectingProvider, reply_template
from chatballs.ai.tool_loop_testing import ScriptedProvider, calls
from chatballs.ai.turn import plan_chat, run_turn_chat, turn_pseudonymizer
from chatballs.ai.turn_skills import LOAD_SKILL
from chatballs.ai.turn_templates import PREPARE_REPLY
from chatballs.conversations.ai_history import conversation_history
from chatballs.conversations.ai_reply_delivery import AiDeliveryFailed, deliver_saved
from chatballs.conversations.ai_turn import run_requested_turn
from chatballs.conversations.email_thread_models import EmailThread, EmailThreadMessage
from chatballs.conversations.models import (
    AiTurnState,
    ConnectionIdentity,
    Contact,
    Conversation,
    Message,
)
from chatballs.conversations.serializers import message_payload
from chatballs.conversations.transports.email_smtp import MailOutcome
from chatballs.events.models import OutboxEvent
from chatballs.integrations.models import Integration
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import system_tenant_context
from chatballs.webchat.message_history import messages_payload
from chatballs.webchat.models import WebSession
from chatballs.webchat.testing import create_web_widget


@override_settings(CHATBALLS_AI_PROVIDER="", CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class TemplateCompletionTests(SkillRuntimeSetup, TestCase):
    def setUp(self):
        super().setUp()
        provider = Integration.objects.create(
            organization=self.organization, name="Demo", kind="LLM_PROVIDER",
            provider="DEMO", secret="demo",
        )
        self.agent.provider_integration = provider
        self.agent.model = "demo"
        self.agent.save(update_fields=["provider_integration", "model"])
        self.skill.templates = [reply_template()]
        self.skill.save(update_fields=["templates"])
        self.contact = Contact.objects.create(organization=self.organization, name="Anna", email="anna@example.test")
        self.web = Integration.objects.create(organization=self.organization, channel=self.agent.channel,
                                              name="Web", kind="MESSENGER", provider="WEB")
        self.conversation = Conversation.objects.create(organization=self.organization, channel=self.agent.channel,
                                                         connection=self.web, contact=self.contact)
        self.incoming = Message.objects.create(conversation=self.conversation, author_type="CONTACT",
                                              text="Status", ai_turn_state=AiTurnState.PENDING)

    def provider(self):
        return SelectingProvider(
            calls((LOAD_SKILL, {"skill_id": str(self.skill.public_id)})),
            calls((PREPARE_REPLY, {"skill_id": str(self.skill.public_id), "template_id": TEMPLATE_ID,
                                  "data": {"title": "[[client_name]]", "amount": 0, "active": False}})),
        )

    def live(self, provider, send=True):
        with patch("chatballs.ai.invocation.get_provider", return_value=provider), patch(
            "chatballs.conversations.transports.send_reply", return_value=send,
        ) as sender:
            run_requested_turn({"messageId": self.incoming.pk, "userId": "visitor"},
                               system_tenant_context(self.organization))
        return sender

    def test_snapshot_survives_delete_and_retry_uses_saved_reply(self):
        provider = self.provider()
        with self.assertRaises(AiDeliveryFailed):
            self.live(provider, send=False)
        reply = Message.objects.get(ai_reply_to=self.incoming)
        before = message_payload(reply)
        self.assertEqual(reply.delivery_representation, "html")
        self.assertEqual(reply.text, "Anna 0 false")
        self.assertIn("Anna", reply.content_html)
        self.assertEqual(self.conversation.domain_events.filter(event_type="PUBLIC_REPLY").count(), 1)
        diagnostic = TurnDiagnostic.objects.get(message=self.incoming).payload
        for item in diagnostic["rounds"]:
            for call in item["response"].get("tool_calls", []):
                self.assertEqual(call["arguments"], {})
            for message in item["request"]["messages"]:
                for call in message.get("tool_calls", []):
                    self.assertEqual(call["arguments"], {})
                if message["role"] == "tool":
                    self.assertEqual(message["content"], "[operation result omitted]")
        self.assertNotIn("Anna", json.dumps(diagnostic))
        self.skill.delete()
        provider = ScriptedProvider(ProviderError("must not run"))
        sender = self.live(provider)
        sender.assert_called_once()
        self.assertEqual(sender.call_args.kwargs["text"], reply.text)
        self.live(provider).assert_not_called()
        self.assertEqual(provider.requests, [])
        reply.refresh_from_db()
        self.assertEqual(message_payload(reply), before)
        self.assertEqual(Message.objects.filter(ai_reply_to=self.incoming).count(), 1)

    def test_live_template_runs_with_runtime_tenant_role(self):
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE chatballs_runtime_app")
        try:
            sender = self.live(self.provider())
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
        sender.assert_called_once()
        self.assertEqual(Message.objects.get(ai_reply_to=self.incoming).format_version, 1)

    def test_human_takeover_cancel_and_deadline_discard_prepared_snapshot(self):
        for mode in ("takeover", "cancel", "deadline"):
            with self.subTest(mode=mode):
                self.conversation.control_mode = "AI"
                self.conversation.save(update_fields=["control_mode"])
                self.incoming.ai_turn_state = AiTurnState.PENDING
                self.incoming.save(update_fields=["ai_turn_state"])
                provider = self.provider()
                chat = provider.chat

                def interrupt(chat=chat, provider=provider, mode=mode, **kwargs):
                    result = chat(**kwargs)
                    if len(provider.requests) == 3:
                        if mode == "takeover":
                            Conversation.objects.filter(pk=self.conversation.pk).update(control_mode="HUMAN")
                        elif mode == "cancel":
                            Message.objects.filter(pk=self.incoming.pk).update(ai_turn_state=AiTurnState.DONE)
                        else:
                            Message.objects.filter(pk=self.incoming.pk).update(created_at=timezone.now() - timedelta(days=1))
                    return result

                with patch.object(provider, "chat", side_effect=interrupt):
                    sender = self.live(provider)
                if mode == "deadline":
                    self.assertEqual(Message.objects.get(ai_reply_to=self.incoming).format_version, 0)
                    self.assertNotIn("Anna", sender.call_args.kwargs["text"])
                else:
                    sender.assert_not_called()
                    self.assertFalse(Message.objects.filter(ai_reply_to=self.incoming).exists())

    def test_planned_template_is_consistent_after_config_edit_and_ai_history_uses_text(self):
        provider = self.provider()
        with tenant_atomic(self.context), patch("chatballs.ai.invocation.get_provider", return_value=provider):
            plan = plan_chat(agent=self.agent, message="Status", conversation=self.conversation,
                             pseudonymizer=turn_pseudonymizer(self.conversation))
        self.skill.templates = []
        self.skill.instruction = "changed"
        self.skill.save()
        self.skill.delete()
        with self.assertNumQueries(0):
            answer = run_turn_chat(plan, time_left=30)
        self.assertEqual(answer.prepared_reply.text, "Anna 0 false")
        Message.objects.create(conversation=self.conversation, author_type="AI",
                               text=answer.prepared_reply.text, content_html=answer.prepared_reply.content_html)
        Message.objects.create(conversation=self.conversation, author_type="CONTACT", text="Next")
        history = conversation_history(self.conversation, 10)
        self.assertEqual(history[-1]["content"], answer.prepared_reply.text)
        with tenant_atomic(self.context), patch("chatballs.ai.invocation.get_provider", return_value=provider):
            next_plan = plan_chat(agent=self.agent, message="Next", history=history,
                                  conversation=self.conversation)
        self.assertNotIn("Anna", repr(next_plan.job.messages))
        self.assertNotIn("<div", repr(next_plan.job.messages))

    def test_verification_chat_returns_same_snapshot_without_creating_customer_records(self):
        provider = self.provider()
        counts = {model: model.objects.count() for model in (Contact, Conversation, Message, OutboxEvent)}
        with patch("chatballs.ai.invocation.get_provider", return_value=provider):
            response = self.client.post(self.chat_url, {"message": "Status", "clientData": {"name": "Anna"}}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["reply"], "Anna 0 false")
        self.assertEqual(response.json()["formatVersion"], 1)
        self.assertEqual(response.json()["deliveryRepresentation"], "html")
        for model, count in counts.items():
            self.assertEqual(model.objects.count(), count)
        self.assertEqual(LlmInvocation.objects.filter(operation="chat").count(), 3)

    def test_transport_matrix_uses_saved_text_and_real_representation(self):
        for provider in ("TELEGRAM", "MAX", "VK", "EMAIL"):
            with self.subTest(provider=provider):
                self.web.provider = provider
                self.web.save(update_fields=["provider"])
                self.conversation.external_chat_id = self.contact.email if provider == "EMAIL" else "chat"
                self.conversation.save(update_fields=["external_chat_id"])
                incoming = Message.objects.create(conversation=self.conversation, author_type="CONTACT",
                                                  text="Status", ai_turn_state=AiTurnState.PENDING)
                self.incoming = incoming
                with patch("chatballs.conversations.ai_reply_delivery.deliver_message", return_value=MailOutcome("SMTP_ACCEPTED")) as smtp:
                    sender = self.live(self.provider())
                reply = Message.objects.get(ai_reply_to=incoming)
                self.assertEqual(reply.delivery_representation, "text")
                if provider == "EMAIL":
                    email = smtp.call_args.args[1]
                    self.assertEqual(email.get_content().strip(), reply.text)
                    self.assertFalse(email.is_multipart())
                else:
                    self.assertEqual(sender.call_args.kwargs["text"], reply.text)

    def test_email_continuation_uses_letter_route_instead_of_original_web(self):
        mailbox = Integration.objects.create(organization=self.organization, name="Mail",
                                              kind="MESSENGER", provider="EMAIL")
        thread = EmailThread.objects.create(conversation=self.conversation, connection=mailbox,
                                            recipient=self.contact.email, subject="Enquiry")
        EmailThreadMessage.objects.create(thread=thread, connection=mailbox, message=self.incoming,
                                           direction="INBOUND", mail_message_id="<incoming@example.test>",
                                           sender_address=self.contact.email, recipient_address="support@example.test")
        with patch("chatballs.conversations.ai_reply_delivery.deliver_message", return_value=MailOutcome("SMTP_ACCEPTED")) as smtp:
            self.live(self.provider()).assert_not_called()
        reply = Message.objects.get(ai_reply_to=self.incoming)
        self.assertEqual(reply.delivery_representation, "text")
        self.assertEqual(smtp.call_args.args[0].pk, mailbox.pk)
        email = smtp.call_args.args[1]
        self.assertEqual(email["In-Reply-To"], "<incoming@example.test>")
        self.assertEqual(email["To"], self.contact.email)
        self.assertEqual(email.get_content().strip(), reply.text)
        self.assertEqual(reply.email_transport.connection_id, mailbox.pk)
        self.assertEqual(self.conversation.domain_events.get(event_type="PUBLIC_REPLY").transport, "EMAIL")
        reply.ai_delivery = {**reply.ai_delivery, "sent": False}
        reply.save(update_fields=["ai_delivery"])
        for disabled in (mailbox, self.web):
            with self.subTest(disabled=disabled.provider):
                disabled.is_active = False
                disabled.save(update_fields=["is_active"])
                with patch("chatballs.conversations.ai_reply_delivery.deliver_message") as smtp:
                    deliver_saved(self.incoming.pk, system_tenant_context(self.organization))
                smtp.assert_not_called()
                disabled.is_active = True
                disabled.save(update_fields=["is_active"])

    def test_prepared_handoff_keeps_snapshot_and_emits_one_public_reply(self):
        provider = self.provider()
        chat = provider.chat

        def handoff(**kwargs):
            result = chat(**kwargs)
            if len(provider.requests) == 3:
                from dataclasses import replace
                result = replace(result, text=result.text + " <<HANDOFF>>")
            return result

        with patch.object(provider, "chat", side_effect=handoff):
            self.live(provider)
        reply = Message.objects.get(ai_reply_to=self.incoming)
        self.assertEqual(reply.text, "Anna 0 false")
        self.assertIn("Anna", reply.content_html)
        self.assertEqual(reply.format_version, 1)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, "PAUSED")
        self.assertEqual(self.conversation.domain_events.filter(event_type="PUBLIC_REPLY").count(), 1)

    def test_public_history_returns_only_its_html_snapshot_and_never_mail_or_skill_configuration(self):
        widget = create_web_widget(self.agent.channel, integration=self.web)
        identity = ConnectionIdentity.objects.create(connection=self.web, contact=self.contact, external_user_id="visitor")
        session = WebSession.objects.create(connection=self.web, widget=widget, identity=identity, token_hash="a" * 64)
        self.live(self.provider())
        reply = Message.objects.get(ai_reply_to=self.incoming)
        mail = Message.objects.create(conversation=self.conversation, author_type="CONTACT",
                                      text="Legacy mail", content_html="<b>Legacy mail</b>")
        Message.objects.create(conversation=self.conversation, author_type="SYSTEM", system_event="tool_called", text="PRIVATE EVENT")
        other_connection = Integration.objects.create(organization=self.organization, channel=self.agent.channel,
                                                       name="Other web", kind="MESSENGER", provider="WEB")
        other_dialog = Conversation.objects.create(organization=self.organization, channel=self.agent.channel,
                                                    connection=other_connection, contact=self.contact)
        Message.objects.create(conversation=other_dialog, author_type="AI", text="PRIVATE DIALOG")
        payload = messages_payload(session, 0)
        shown = {item["id"]: item for item in payload["messages"]}
        self.assertEqual(shown[reply.pk]["contentHtml"], reply.content_html)
        self.assertEqual(shown[reply.pk]["presentation"], reply.presentation)
        self.assertNotIn("contentHtml", shown[mail.pk])
        serialized = json.dumps(payload)
        for value in ("PRIVATE DIALOG", "PRIVATE EVENT", "instruction", "ai_delivery", "sourceLetterId", "examples"):
            self.assertNotIn(value, serialized)
        self.assertNotIn("presentation", message_payload(mail))
        reply.delivery_representation = "text"
        reply.save(update_fields=["delivery_representation"])
        shown = {item["id"]: item for item in messages_payload(session, 0)["messages"]}
        self.assertNotIn("presentation", shown[reply.pk])
