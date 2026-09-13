"""Очередь к оператору: с какого момента идёт ожидание и в каком порядке разбирают.

Регрессия, ради которой заведён waiting_since: «дольше всех ждущий» считался по
времени последнего сообщения, поэтому клиент, напомнивший о себе, уезжал в конец
очереди. Чем настойчивее человек, тем позже до него доходили руки.
"""

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from chatballs.ai.models import AIAgent
from chatballs.channels.models import Channel
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import ControlMode, Conversation
from chatballs.conversations.selectors import order_conversations
from chatballs.conversations.services import (
    claim_conversation,
    close_conversation,
    return_to_queue,
)
from chatballs.conversations.transports.base import InboundMessage
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import HumanUser, Organization
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.notifications.models import Notification, NotificationType
from chatballs.testing import tenant_context_for


class QueueTestBase(TestCase):
    def setUp(self) -> None:
        bootstrap_owner(email="owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.owner = HumanUser.objects.get(email="owner@example.com")
        self.context = tenant_context_for(self.owner, self.organization)
        # Канал без активного агента: каждый входящий сразу создаёт очередь.
        self.channel = Channel.objects.create(
            organization=self.organization, code="queue-order", name="Очередь"
        )
        self.integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.TELEGRAM,
            name="queue-bot",
            channel=self.channel,
        )

    def _ingest(self, external_id: str, chat_id: str, text: str) -> None:
        inbound = InboundMessage(
            external_id=external_id,
            user_id=chat_id,
            chat_id=chat_id,
            text=text,
            display_name=chat_id,
        )
        with (
            mock.patch("chatballs.conversations.ingest.run_channel_turn"),
            mock.patch("chatballs.conversations.ingest.transports.send_reply"),
        ):
            ingest_inbound(self.integration, inbound)

    def _waiting_order(self) -> list[int]:
        ordered, _ = order_conversations(
            Conversation.objects.filter(organization=self.organization), "waiting"
        )
        return list(ordered.values_list("id", flat=True))



class QueueOrderTests(QueueTestBase):
    def test_new_dialog_without_agent_starts_waiting(self) -> None:
        self._ingest("m-1", "chat-1", "Здравствуйте")
        conversation = self.channel.conversations.get()
        self.assertEqual(conversation.control_mode, ControlMode.PAUSED)
        self.assertIsNotNone(conversation.waiting_since)

    def test_reminder_from_customer_does_not_restart_the_wait(self) -> None:
        self._ingest("m-1", "chat-1", "Здравствуйте")
        conversation = self.channel.conversations.get()
        started = conversation.waiting_since

        self._ingest("m-2", "chat-1", "Ну что там?")

        conversation.refresh_from_db()
        self.assertEqual(conversation.waiting_since, started)
        # Свежесть диалога при этом обновилась — ожидание и активность разные вещи.
        self.assertGreater(conversation.last_message_at, started)

    def test_longest_waiting_goes_first_even_after_a_reminder(self) -> None:
        self._ingest("a-1", "chat-a", "Первый вопрос")
        first = Conversation.objects.get(external_chat_id="chat-a")
        # Первый диалог ждёт заметно дольше второго.
        Conversation.objects.filter(pk=first.pk).update(
            waiting_since=timezone.now() - timedelta(hours=2)
        )
        self._ingest("b-1", "chat-b", "Второй вопрос")
        second = Conversation.objects.get(external_chat_id="chat-b")

        # …и именно он напоминает о себе, двигая своё последнее сообщение вперёд.
        self._ingest("a-2", "chat-a", "Всё ещё жду")

        self.assertEqual(self._waiting_order(), [first.id, second.id])

    def test_claim_ends_the_wait_and_return_to_queue_starts_a_new_one(self) -> None:
        self._ingest("m-1", "chat-1", "Здравствуйте")
        conversation = self.channel.conversations.get()
        first_wait = conversation.waiting_since

        claimed = claim_conversation(context=self.context, conversation_id=conversation.id)
        self.assertEqual(claimed.control_mode, ControlMode.HUMAN)
        self.assertIsNone(claimed.waiting_since)

        returned = return_to_queue(context=self.context, conversation_id=conversation.id)
        self.assertEqual(returned.control_mode, ControlMode.PAUSED)
        self.assertIsNotNone(returned.waiting_since)
        # Ожидание началось заново: диалог успел побывать у оператора.
        self.assertGreater(returned.waiting_since, first_wait)

    def test_closed_dialog_leaves_the_queue(self) -> None:
        self._ingest("z-1", "chat-z", "Вопрос")
        conversation = self.channel.conversations.get()
        self.assertIsNotNone(conversation.waiting_since)

        closed = close_conversation(context=self.context, conversation_id=conversation.id)
        self.assertIsNone(closed.waiting_since)


class NewDialogNotificationTests(QueueTestBase):
    """«Новый диалог» и «клиент запросил оператора» — разные события.

    Диалог начинается и на канале с работающим агентом, где человека никто не
    звал. Назвать такой оклик просьбой о человеке — соврать тому, кто на него
    подписан.
    """

    def _last_type(self) -> str:
        return (
            Notification.objects.filter(organization=self.organization)
            .order_by("-id")
            .values_list("type", flat=True)
            .first()
        )

    def test_dialog_without_an_agent_asks_for_a_person(self) -> None:
        self._ingest("n-1", "chat-n", "Здравствуйте")
        self.assertEqual(self._last_type(), NotificationType.OPERATOR_REQUESTED)

    def test_dialog_handled_by_the_agent_is_just_a_new_dialog(self) -> None:
        agent = AIAgent.objects.create(
            organization=self.organization,
            channel=self.channel,
            name="Консультант",
            is_active=True,
        )
        self.assertTrue(agent.is_active)
        with mock.patch(
            "chatballs.conversations.ingest.run_channel_turn",
            return_value=mock.Mock(text="Здравствуйте!"),
        ), mock.patch("chatballs.conversations.ingest.transports.send_reply"):
            ingest_inbound(
                self.integration,
                InboundMessage(
                    external_id="a-1",
                    user_id="chat-a",
                    chat_id="chat-a",
                    text="Здравствуйте",
                    display_name="chat-a",
                ),
            )
        self.assertEqual(self._last_type(), NotificationType.NEW_DIALOG)
