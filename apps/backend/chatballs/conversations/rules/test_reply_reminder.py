"""Напоминание ответить: принятое обращение, серии сообщений клиента и отмена."""

from datetime import timedelta

from django.test import TestCase

from chatballs.conversations.models import Conversation
from chatballs.conversations.rules.models import HandlingRuleKind
from chatballs.conversations.rules.notification_test_base import NotificationScene
from chatballs.conversations.services import (
    assign_operator,
    claim_conversation,
    close_conversation,
    mark_conversation_as_spam,
    post_operator_message,
)

REMINDER = HandlingRuleKind.REPLY_REMINDER


class ReplyReminderTests(NotificationScene, TestCase):
    slug = "reply-reminder"
    key = "notifications.reply_reminder"

    def setUp(self) -> None:
        super().setUp()
        self.enable(REMINDER, delay_minutes=4, recipients=["ASSIGNEE", "GROUP_SUPERVISORS"])
        self.dialog = self.receive("first")
        self.operator_context = self.as_user(self.operator)
        claim_conversation(context=self.operator_context, conversation_id=self.dialog.pk)

    def reminders(self):
        return self.executions(self.dialog).filter(action="REMIND_REPLY").order_by("id")

    def reply(self, text: str = "Answer") -> None:
        post_operator_message(
            context=self.operator_context, conversation=Conversation.objects.get(pk=self.dialog.pk),
            text=text,
        )

    def test_accepting_a_waiting_customer_starts_the_reminder(self) -> None:
        accepted = self.dialog.domain_events.get(event_type="ACCEPTED")
        execution = self.reminders().get()
        # Клиент написал ещё в очереди: срок идёт с момента принятия.
        self.assertEqual(
            (execution.source_event_id, execution.started_at, execution.scheduled_for),
            (accepted.pk, accepted.occurred_at, accepted.occurred_at + timedelta(minutes=4)),
        )
        self.deliver(execution)
        self.assertEqual(self.notified(self.key), {self.operator.user_id, self.lead.user_id})
        self.assertEqual(self.status(execution), ("EXECUTED", ""))

    def test_reply_cancels_and_a_new_series_waits_again(self) -> None:
        first = self.reminders().get()
        self.reply()
        self.assertEqual(self.status(first), ("SKIPPED", "replied"))
        self.assertEqual(self.reminders().count(), 1)

        # Новая серия после ответа человека: срок от её первого сообщения.
        self.receive("series-1")
        second = self.reminders().exclude(pk=first.pk).get()
        answer = self.dialog.domain_events.filter(event_type="PUBLIC_REPLY").latest("sequence")
        opening = self.dialog.messages.filter(author_type="CONTACT").latest("id")
        self.assertEqual(
            (second.source_event_id, second.started_at, second.scheduled_for),
            (answer.pk, opening.created_at, opening.created_at + timedelta(minutes=4)),
        )
        # Следующие сообщения той же серии срок не сдвигают и второй записи не дают.
        for number in (2, 3):
            self.receive(f"series-{number}")
        self.assertEqual(self.reminders().count(), 2)
        self.assertEqual(self.reminders().get(pk=second.pk).scheduled_for, second.scheduled_for)
        self.assertEqual(self.due_events(second).get().next_attempt_at, second.scheduled_for)

        self.deliver(second)
        self.assertEqual(self.status(second), ("EXECUTED", ""))
        # После напоминания серия продолжается — ещё одного она не получает.
        self.receive("series-4")
        self.assertEqual(self.reminders().count(), 2)
        self.assertEqual(self.notices(self.key).count(), 2)

        self.reply("Second answer")
        self.receive("next-series")
        third = self.reminders().exclude(pk__in=[first.pk, second.pk]).get()
        self.assertEqual(self.status(third), ("PENDING", ""))
        self.deliver(third)
        self.assertEqual(self.notices(self.key).count(), 4)

    def test_reminder_is_cancelled_when_the_condition_is_gone(self) -> None:
        self.reply()
        cases = (
            ("replied", self.reply),
            ("assignment_replaced", lambda: assign_operator(
                context=self.context, conversation_id=self.dialog.pk, assignee=self.colleague.user)),
            ("conversation_not_open", lambda: close_conversation(
                context=self.context, conversation_id=self.dialog.pk)),
        )
        for number, (reason, change) in enumerate(cases):
            with self.subTest(reason=reason):
                self.receive(f"case-{number}")
                execution = self.reminders().filter(status="PENDING").get()
                change()
                self.assertEqual(self.status(execution), ("SKIPPED", reason))
                self.deliver(execution)
                if reason == "assignment_replaced":
                    # Новый ответственный принимает диалог и отвечает за него сам.
                    claim_conversation(
                        context=self.as_user(self.colleague), conversation_id=self.dialog.pk
                    )
                    fresh = self.reminders().filter(status="PENDING").get()
                    self.assertEqual(fresh.source_event.event_type, "ACCEPTED")
                    self.operator_context = self.as_user(self.colleague)
                    self.reply()
        self.assertFalse(self.notices(self.key).exists())

    def test_leaving_human_handling_cancels_the_pending_reminder_immediately(self) -> None:
        execution = self.reminders().get()
        mark_conversation_as_spam(context=self.context, conversation_id=self.dialog.pk)
        self.assertEqual(self.dialog.domain_events.filter(event_type="QUEUE_EXITED").count(), 2)
        self.assertEqual(self.status(execution), ("SKIPPED", "conversation_not_open"))
        self.deliver(execution)
        self.assertFalse(self.notices(self.key).exists())

    def test_state_changed_past_the_facts_is_checked_when_the_time_comes(self) -> None:
        execution = self.reminders().get()
        # Диалог вернули AI в обход фактов: проверка в срок — последняя.
        Conversation.objects.filter(pk=self.dialog.pk).update(control_mode="AI")
        self.deliver(execution)
        self.assertEqual(self.status(execution), ("SKIPPED", "not_waiting"))
        self.assertFalse(self.notices(self.key).exists())
