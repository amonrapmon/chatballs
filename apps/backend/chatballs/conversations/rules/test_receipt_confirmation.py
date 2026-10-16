"""Подтверждение получения: настроенный текст, один раз и только когда есть что сказать."""

from unittest import mock

from django.test import TestCase

from chatballs.conversations.models import Conversation, MessageAuthor
from chatballs.conversations.rules.message_delivery import DeliveryFailed
from chatballs.conversations.rules.models import HandlingRule, HandlingRuleKind
from chatballs.conversations.rules.receipt_confirmation import RULE_MESSAGE_DELIVERY
from chatballs.conversations.rules.rule_test_base import RuleScene
from chatballs.conversations.rules.settings import update_rule
from chatballs.conversations.services import claim_conversation, return_to_queue
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.integrations.models import Integration
from chatballs.testing import tenant_context_for

CONFIRMATION = HandlingRuleKind.RECEIPT_CONFIRMATION
SEND = "chatballs.conversations.rules.message_delivery.transports.send_reply"


class ReceiptConfirmationTests(RuleScene, TestCase):
    slug = "receipt-confirmation"

    def setUp(self) -> None:
        super().setUp()
        # Мессенджер, а не виджет: у него есть настоящая отправка наружу.
        self.telegram = Integration.objects.create(
            organization=self.organization, kind="MESSENGER", provider="TELEGRAM",
            name="Telegram", channel=self.channel,
        )

    def confirmations(self, conversation: Conversation):
        return conversation.messages.filter(external_id__startswith="rule-execution:")

    def deliveries(self):
        return OutboxEvent.objects.filter(event_type=RULE_MESSAGE_DELIVERY).order_by("created_at")

    def run_due(self, conversation: Conversation) -> None:
        for execution in self.executions(conversation):
            self.deliver(execution)

    def status(self, conversation: Conversation) -> tuple[str, str]:
        execution = self.executions(conversation).get()
        return execution.status, execution.reason

    def test_confirmation_carries_the_configured_text_and_deadline_to_the_source_connection(
        self,
    ) -> None:
        self.enable(CONFIRMATION, delay_minutes=90, text="Мы получили обращение. Ответим через {срок}.")
        conversation = self.receive("first", connection=self.telegram)
        waiting_since = conversation.waiting_since
        execution = self.executions(conversation).get()
        entry = conversation.domain_events.get(event_type="QUEUE_ENTERED")
        # Срок правила — обещание клиенту, а не отсрочка: отправка идёт сразу.
        self.assertEqual(
            (execution.source_event_id, execution.action, execution.scheduled_for),
            (entry.pk, "SEND_CONFIRMATION", entry.occurred_at),
        )
        self.run_due(conversation)

        message = self.confirmations(conversation).get()
        self.assertEqual(
            (message.author_type, message.text),
            (MessageAuthor.SYSTEM, "Мы получили обращение. Ответим через 1 час 30 минут."),
        )
        execution.refresh_from_db()
        self.assertEqual((execution.status, execution.message_id), ("EXECUTED", message.pk))
        # Подтверждение — не ответ: ожидание и очередь остаются как были.
        conversation.refresh_from_db()
        self.assertEqual(
            (conversation.control_mode, conversation.waiting_since), ("PAUSED", waiting_since)
        )
        self.assertFalse(conversation.domain_events.filter(event_type="PUBLIC_REPLY").exists())
        with mock.patch(SEND, return_value=True) as send:
            dispatch(self.deliveries().get())
        send.assert_called_once_with(
            self.telegram, chat_id="client", user_id="client",
            text="Мы получили обращение. Ответим через 1 час 30 минут.",
        )

    def test_deadline_is_worded_in_the_organization_language(self) -> None:
        self.organization.language = "en"
        self.organization.save(update_fields=["language"])
        cases = ((1, "1 minute"), (45, "45 minutes"), (60, "1 hour"), (150, "2 hours 30 minutes"))
        for number, (minutes, words) in enumerate(cases):
            with self.subTest(minutes=minutes):
                # Метку срока узнают на любом языке интерфейса.
                self.enable(CONFIRMATION, delay_minutes=minutes, text="Reply in {deadline} / {срок}")
                conversation = self.receive(f"en-{number}", user=f"client-{number}")
                self.run_due(conversation)
                self.assertEqual(
                    self.confirmations(conversation).get().text, f"Reply in {words} / {words}"
                )
        self.organization.language = "ru"
        self.organization.save(update_fields=["language"])
        for number, (minutes, words) in enumerate(
            ((1, "1 минута"), (2, "2 минуты"), (5, "5 минут"), (120, "2 часа"), (1440, "24 часа"))
        ):
            with self.subTest(minutes=minutes):
                self.enable(CONFIRMATION, delay_minutes=minutes, text="Срок: {срок}")
                conversation = self.receive(f"ru-{number}", user=f"visitor-{number}")
                self.run_due(conversation)
                self.assertEqual(self.confirmations(conversation).get().text, f"Срок: {words}")

    def test_repeated_event_and_repeated_queue_entry_do_not_confirm_twice(self) -> None:
        self.enable(CONFIRMATION, delay_minutes=15, text="Received, {срок}")
        conversation = self.receive("first", connection=self.telegram)
        event = self.due_events(self.executions(conversation).get()).get()
        OutboxEvent.objects.create(
            aggregate_type=event.aggregate_type, aggregate_id=event.aggregate_id,
            event_type=event.event_type, payload=event.payload, ownership=event.ownership,
            organization=event.organization, actor_kind=event.actor_kind,
        )
        for _ in range(2):
            self.run_due(conversation)
        # Клиент пишет ещё, диалог берут и возвращают в очередь: обращение то же.
        self.receive("second", connection=self.telegram)
        operator = tenant_context_for(self.operator.user, self.organization)
        claim_conversation(context=operator, conversation_id=conversation.pk)
        return_to_queue(context=operator, conversation_id=conversation.pk)
        self.run_due(conversation)

        self.assertEqual(conversation.domain_events.filter(event_type="QUEUE_ENTERED").count(), 2)
        self.assertEqual(
            (self.executions(conversation).count(), self.confirmations(conversation).count(),
             self.deliveries().count()),
            (1, 1, 1),
        )

    def test_only_the_configured_text_leaves_and_delivery_failure_is_retried(self) -> None:
        self.enable(CONFIRMATION, delay_minutes=15, text="Received, {срок}")
        conversation = self.receive("first", connection=self.telegram)
        self.run_due(conversation)
        event = self.deliveries().get()
        # В событии только ссылка на запись ленты: ни текста, ни настроек подключения.
        self.assertEqual(event.payload, {"messageId": self.confirmations(conversation).get().pk})
        with mock.patch(SEND, return_value=False) as send, self.assertRaises(DeliveryFailed) as failed:
            dispatch(event)
        self.assertNotIn("Received", str(failed.exception))
        self.assertEqual(send.call_args.kwargs["text"], "Received, 15 минут")
        # Повтор события отправляет ту же запись, второй в ленте не появляется.
        with mock.patch(SEND, return_value=True) as send:
            dispatch(event)
        self.assertEqual(send.call_args.kwargs["text"], "Received, 15 минут")
        self.assertEqual(self.confirmations(conversation).count(), 1)

    def test_disabled_rule_and_missing_settings_send_nothing(self) -> None:
        # Правило выключено с рождения: клиент ничего не получает.
        silent = self.receive("silent", user="silent")
        self.assertFalse(self.executions(silent).exists())

        self.enable(CONFIRMATION, delay_minutes=15, text="Received, {срок}")
        cases = (
            ("rule_disabled", lambda: update_rule(
                context=self.context, kind=CONFIRMATION, changes={"enabled": False})),
            # Текст убрали мимо проверки настроек: своего у сервера нет.
            ("settings_incomplete", lambda: HandlingRule.objects.filter(kind=CONFIRMATION).update(
                text="  ")),
            ("condition_not_met", lambda: HandlingRule.objects.filter(kind=CONFIRMATION).update(
                conditions={"channelIds": [self.channel.pk + 1000]})),
            ("connection_missing", lambda: Conversation.objects.filter(
                contact__name="Client").update(connection=None)),
            ("not_waiting", lambda: claim_conversation(
                context=self.context,
                conversation_id=Conversation.objects.filter(contact__name="Client").latest("id").pk,
            )),
        )
        for number, (reason, change) in enumerate(cases):
            with self.subTest(reason=reason):
                conversation = self.receive(f"case-{number}", user=f"case-{number}")
                change()
                self.run_due(conversation)
                self.assertEqual(self.status(conversation), ("SKIPPED", reason))
                self.assertFalse(self.confirmations(conversation).exists())
                HandlingRule.objects.filter(kind=CONFIRMATION).update(
                    enabled=True, text="Received, {срок}", conditions={}
                )
        self.assertFalse(self.deliveries().exists())

    def test_rule_limited_to_other_channels_plans_nothing(self) -> None:
        self.enable(
            CONFIRMATION, delay_minutes=15, text="Received",
            conditions={"channelIds": [self.channel.pk]},
        )
        matching = self.receive("matching")
        self.assertEqual(self.executions(matching).count(), 1)
        HandlingRule.objects.filter(kind=CONFIRMATION).update(
            conditions={"channelIds": [self.channel.pk + 1000]}
        )
        other = self.receive("other", user="other")
        self.assertFalse(self.executions(other).exists())
