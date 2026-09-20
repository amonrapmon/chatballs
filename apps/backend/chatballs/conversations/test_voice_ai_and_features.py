"""AI отвечает текстом на голосовое (по стенограмме) и настройка «Голосовые и
звонки» по точкам входа."""

from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from chatballs.ai.models import AIAgent, AIAgentStatus
from chatballs.ai.provider.base import ProviderError
from chatballs.channels.models import Channel
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import ControlMode, MessageAuthor, MessageKind, TranscriptStatus
from chatballs.conversations.transports.base import InboundMessage
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.tenancy.database import tenant_atomic
from chatballs.conversations import ai_turn
from chatballs.testing import TenantAPIClient as APIClient, ai_answer, run_pending_ai_turns


class VoiceAiReplyTests(TestCase):
    def setUp(self) -> None:
        bootstrap_owner(email="owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.channel = Channel.objects.create(organization=self.organization, code="line", name="Линия")
        AIAgent.objects.create(channel=self.channel, name="Агент", model="openai/gpt-4o-mini", status=AIAgentStatus.ACTIVE)
        self.integration = Integration.objects.create(
            organization=self.organization, kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.TELEGRAM, name="Bot", secret="token", channel=self.channel
        )
        self.inbound = InboundMessage(external_id="v-1", user_id="u-1", chat_id="c-1", text="", display_name="Ольга", voice_file_id="f-1", voice_duration=5, voice_mime="audio/ogg")

    def _ingest(self, transcribe, answer="Ответ"):
        """Приём голосового и ход AI по нему.

        Расшифровка — обращение к провайдеру, поэтому она идёт не в приёме, а
        в ходе (chatballs.conversations.ai_turn); тест повторяет этот порядок.
        """
        with (
            mock.patch("chatballs.conversations.ingest.transports.download_voice", return_value=(b"OGG", "audio/ogg")),
            mock.patch("chatballs.conversations.transports.send_reply", return_value=True) as send,
            mock.patch("chatballs.ai.provider.local.LocalProvider.transcribe", **transcribe),
            mock.patch("chatballs.conversations.ai_turn.plan_chat", wraps=ai_turn.plan_chat) as plan,
            ai_answer(answer),
            tenant_atomic(self.organization.id),
        ):
            ingest_inbound(self.integration, self.inbound)
            run_pending_ai_turns()
        return send, plan

    def test_ai_answers_voice_by_transcript(self) -> None:
        send, plan = self._ingest(
            {"return_value": "Можно оформить возврат?"},
            answer="Да, возврат возможен в течение 14 дней.",
        )
        conversation = self.channel.conversations.get()
        voice = conversation.messages.get(kind=MessageKind.VOICE)
        self.assertEqual(voice.transcript, "Можно оформить возврат?")
        self.assertEqual(voice.transcript_status, TranscriptStatus.READY)
        plan.assert_called_once()
        self.assertEqual(plan.call_args.kwargs["message"], "Можно оформить возврат?")
        reply = conversation.messages.get(author_type=MessageAuthor.AI)
        self.assertIn("возврат", reply.text)
        send.assert_called_once()
        self.assertEqual(conversation.control_mode, ControlMode.AI)

    def test_without_transcription_dialog_goes_to_operator(self) -> None:
        send, plan = self._ingest({"side_effect": ProviderError("нет STT")})
        conversation = self.channel.conversations.get()
        voice = conversation.messages.get(kind=MessageKind.VOICE)
        self.assertEqual(voice.transcript_status, TranscriptStatus.FAILED)
        plan.assert_not_called()
        send.assert_not_called()
        self.assertEqual(conversation.control_mode, ControlMode.PAUSED)

    def test_transcript_is_in_ai_history(self) -> None:
        from chatballs.conversations.ai_turn import _history

        self._ingest({"return_value": "Первый вопрос"})
        conversation = self.channel.conversations.get()
        conversation.messages.create(author_type=MessageAuthor.CONTACT, text="Второй")
        roles = [(h["role"], h["content"]) for h in _history(conversation, 20)]
        self.assertEqual(roles, [("user", "Первый вопрос"), ("assistant", "Ответ")])

    def test_ai_history_window_follows_agent_setting(self) -> None:
        self.channel.ai_agent.history_limit = 3
        self.channel.ai_agent.save(update_fields=["history_limit"])
        self._ingest({"return_value": "Первый вопрос"})
        conversation = self.channel.conversations.get()
        for number in range(1, 6):
            conversation.messages.create(author_type=MessageAuthor.CONTACT, text=f"Сообщение {number}")
        self.inbound = InboundMessage(external_id="t-2", user_id="u-1", chat_id="c-1", text="Последнее", display_name="Ольга")
        _, plan = self._ingest({"return_value": ""})
        history = [item["content"] for item in plan.call_args.kwargs["history"]]
        # Три сообщения перед новым; само новое уходит модели отдельно.
        self.assertEqual(history, ["Сообщение 3", "Сообщение 4", "Сообщение 5"])
        self.assertEqual(plan.call_args.kwargs["message"], "Последнее")


class CommunicationSettingsTests(TestCase):
    def setUp(self) -> None:
        bootstrap_owner(email="owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.channel = Channel.objects.create(organization=self.organization, code="line", name="Линия")
        self.telegram = Integration.objects.create(organization=self.organization, kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.TELEGRAM, name="Bot", secret="t", channel=self.channel)
        self.email = Integration.objects.create(organization=self.organization, kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.EMAIL, name="Почта", secret="p", channel=self.channel)
        self.client = APIClient()
        self.client.login(username="owner@example.com", password="temporary-password")

    def test_matrix_lists_entry_points_and_saves_flags(self) -> None:
        items = self.client.get("/api/v1/company/administration/communication/").json()["items"]
        by_id = {i["id"]: i for i in items}
        self.assertTrue(by_id[self.telegram.id]["voiceMessages"])
        self.assertTrue(by_id[self.telegram.id]["supportsCalls"])
        self.assertFalse(by_id[self.email.id]["supportsCalls"])
        self.assertFalse(by_id[self.email.id]["audioCalls"])

        response = self.client.patch(
            "/api/v1/company/administration/communication/",
            {"items": [{"id": self.telegram.id, "voiceMessages": False, "videoCalls": False}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.telegram.refresh_from_db()
        self.assertFalse(self.telegram.voice_messages_enabled)
        self.assertTrue(self.telegram.audio_calls_enabled)
        self.assertFalse(self.telegram.video_calls_enabled)

    def test_disabled_voice_blocks_operator_and_widget(self) -> None:
        from chatballs.conversations.models import Contact, Conversation

        self.telegram.voice_messages_enabled = False
        self.telegram.save(update_fields=["voice_messages_enabled"])
        contact = Contact.objects.create(organization=self.organization, name="Ольга")
        conversation = Conversation.objects.create(organization=self.organization, channel=self.channel, connection=self.telegram, contact=contact, external_chat_id="c-1")
        with mock.patch("chatballs.conversations.transports.send_voice", return_value=True) as send:
            response = self.client.post(
                f"/api/v1/conversations/{conversation.id}/voice/",
                data={"audio": SimpleUploadedFile("voice.webm", b"WEBM", content_type="audio/webm")},
                format="multipart",
            )
        self.assertEqual(response.status_code, 400)
        send.assert_not_called()
        detail = self.client.get(f"/api/v1/conversations/{conversation.id}/").json()["conversation"]
        self.assertFalse(detail["connection"]["voiceMessages"])
        self.assertTrue(detail["connection"]["audioCalls"])

    def test_disabled_calls_block_call_request(self) -> None:
        from chatballs.calls.errors import CallAccessDenied
        from chatballs.calls.services import create_call_request
        from chatballs.conversations.models import ConnectionIdentity, Contact, Conversation
        from chatballs.tenancy.context import TenantContext

        self.telegram.video_calls_enabled = False
        self.telegram.save(update_fields=["video_calls_enabled"])
        contact = Contact.objects.create(organization=self.organization, name="Ольга")
        ConnectionIdentity.objects.create(contact=contact, connection=self.telegram, external_user_id="u-1", display_name="Ольга")
        conversation = Conversation.objects.create(organization=self.organization, channel=self.channel, connection=self.telegram, contact=contact, external_chat_id="c-1")
        from chatballs.identity.models import HumanUser, OrganizationMembership

        owner = HumanUser.objects.get(email="owner@example.com")
        membership = OrganizationMembership.objects.get(user=owner, organization=self.organization)
        context = TenantContext.for_membership(membership)
        with tenant_atomic(self.organization.id):
            with self.assertRaises(CallAccessDenied):
                create_call_request(context=context, conversation_id=conversation.id, kind="VIDEO")

    def test_employee_cannot_change_matrix(self) -> None:
        from chatballs.identity.models import EmployeeRole, HumanUser, OrganizationMembership

        employee = HumanUser.objects.create_user(email="staff@example.com", password="Password-123")
        OrganizationMembership.objects.create(organization=self.organization, user=employee, role=EmployeeRole.EMPLOYEE, position_title="Op")
        client = APIClient()
        client.force_authenticate(employee)
        self.assertEqual(client.patch("/api/v1/company/administration/communication/", {"items": []}, format="json").status_code, 403)
