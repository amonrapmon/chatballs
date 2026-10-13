"""Уведомление о превышении ожидания: срок, получатели по доступу и штатная доставка."""

from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from chatballs.conversations.rules.models import HandlingRuleKind
from chatballs.conversations.rules.notification_test_base import NotificationScene
from chatballs.conversations.services import (
    claim_conversation,
    close_conversation,
    return_to_queue,
)
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.identity.models import OrganizationMembership
from chatballs.integrations.models import Integration
from chatballs.notifications.delivery import NOTIFICATION_CREATED
from chatballs.notifications.models import MessengerBinding
from chatballs.notifications.preferences import update_preference
from chatballs.notifications.realtime import user_group
from chatballs.notifications.recipients import recipient_user_ids
from chatballs.notifications.selectors import visible_for

NOTICE = HandlingRuleKind.WAIT_EXCEEDED_NOTICE


class WaitExceededNoticeTests(NotificationScene, TestCase):
    slug = "wait-notice"
    key = "notifications.wait_exceeded"

    def test_notice_follows_the_configured_wait_and_reaches_those_with_access(self) -> None:
        self.enable(NOTICE, delay_minutes=7, recipients=["GROUP_SUPERVISORS", "MANAGEMENT"])
        conversation = self.receive("first")
        entry = conversation.domain_events.get(event_type="QUEUE_ENTERED")
        execution = self.executions(conversation).get()
        self.assertEqual(
            (execution.source_event_id, execution.action, execution.scheduled_for),
            (entry.pk, "NOTIFY_WAIT_EXCEEDED", entry.occurred_at + timedelta(minutes=7)),
        )
        # Повторное сообщение клиента прежнее ожидание не обнуляет.
        self.receive("again")
        self.assertEqual(self.executions(conversation).get().scheduled_for, execution.scheduled_for)
        self.assertEqual(self.due_events(execution).get().next_attempt_at, execution.scheduled_for)

        self.deliver(execution)
        # Супервизор чужой группы и рядовые сотрудники не в круге получателей.
        expected = {self.lead.user_id, self.owner.user_id}
        self.assertEqual(self.notified(self.key), expected)
        execution.refresh_from_db()
        self.assertEqual(
            (execution.status, set(execution.recipient_user_ids)), ("EXECUTED", expected)
        )
        self.assertIn(execution.notification_id, set(self.notices(self.key).values_list("pk", flat=True)))
        for notice in self.notices(self.key):
            # Штатный путь: тип из списка подписок, своё событие доставки и
            # повторная проверка доступа перед отправкой.
            self.assertEqual(
                (notice.type, notice.audience, notice.source_id, notice.text_params["minutes"]),
                ("DIALOG_WAITING_LONG", "USER", str(conversation.pk), 7),
            )
            self.assertTrue(OutboxEvent.objects.filter(
                event_type=NOTIFICATION_CREATED, aggregate_id=str(notice.pk)
            ).exists())
            self.assertEqual(recipient_user_ids(notice), [notice.recipient_user_id])
        self.assertTrue(visible_for(self.as_user(self.lead)).filter(title_key=self.key).exists())
        self.assertFalse(visible_for(self.as_user(self.outsider)).filter(title_key=self.key).exists())

    def test_browser_and_messenger_deliver_independently_by_their_own_rules(self) -> None:
        self.enable(NOTICE, delay_minutes=7, recipients=["GROUP_SUPERVISORS", "MANAGEMENT"])
        bot = Integration.objects.create(
            organization=self.organization, kind="MESSENGER", provider="TELEGRAM", name="Notifier"
        )
        for membership, chat in ((self.lead, "lead-chat"), (self.owner, "owner-chat")):
            MessengerBinding.objects.create(
                user=membership.user, integration=bot, external_chat_id=chat
            )
        # Супервизор подписал мессенджер на этот тип; у владельца обычный набор без него.
        update_preference(
            organization_id=self.organization.pk, user_id=self.lead.user_id,
            transport="MESSENGER", types=["DIALOG_WAITING_LONG"],
        )
        conversation = self.receive("first")
        self.deliver(self.executions(conversation).get())

        events = OutboxEvent.objects.filter(
            event_type=NOTIFICATION_CREATED,
            aggregate_id__in=[str(pk) for pk in self.notices(self.key).values_list("pk", flat=True)],
        )
        self.assertEqual(events.count(), 2)
        with mock.patch("chatballs.notifications.realtime.publish") as publish, mock.patch(
            "chatballs.notifications.delivery.transports.send_reply", return_value=True
        ) as send:
            for event in events:
                dispatch(event)
        # Открытое приложение узнаёт у обоих; мессенджер — только по подписке.
        self.assertEqual(
            {call.args[0] for call in publish.call_args_list},
            {user_group(self.lead.user_id), user_group(self.owner.user_id)},
        )
        self.assertEqual([call.kwargs["chat_id"] for call in send.call_args_list], ["lead-chat"])
        self.assertIn("7", send.call_args.kwargs["text"])

    def test_repeated_work_does_not_notify_twice(self) -> None:
        self.enable(NOTICE, delay_minutes=7, recipients=["CONVERSATION_GROUP"])
        conversation = self.receive("first")
        execution = self.executions(conversation).get()
        event = self.due_events(execution).get()
        OutboxEvent.objects.create(
            aggregate_type=event.aggregate_type, aggregate_id=event.aggregate_id,
            event_type=event.event_type, payload=event.payload, ownership=event.ownership,
            organization=event.organization, actor_kind=event.actor_kind,
        )
        for _ in range(2):
            self.deliver(execution)
        group = {self.operator.user_id, self.colleague.user_id}
        self.assertEqual(self.notified(self.key), group)
        self.assertEqual(self.notices(self.key).count(), len(group))

    def test_notice_is_cancelled_when_the_wait_ends(self) -> None:
        self.enable(NOTICE, delay_minutes=7, recipients=["MANAGEMENT"])
        operator = self.as_user(self.operator)
        cases = (
            ("not_waiting", lambda pk: claim_conversation(context=operator, conversation_id=pk)),
            ("conversation_not_open", lambda pk: close_conversation(
                context=self.context, conversation_id=pk)),
        )
        for number, (reason, change) in enumerate(cases):
            with self.subTest(reason=reason):
                conversation = self.receive(f"case-{number}", user=f"case-{number}")
                execution = self.executions(conversation).get()
                change(conversation.pk)
                # Отменено сразу, не дожидаясь срока; поздний воркер ничего не шлёт.
                self.assertEqual(self.status(execution), ("SKIPPED", reason))
                self.deliver(execution)
        self.assertFalse(self.notices(self.key).exists())

    def test_new_wait_gets_its_own_notice(self) -> None:
        self.enable(NOTICE, delay_minutes=7, recipients=["MANAGEMENT"])
        conversation = self.receive("first")
        first = self.executions(conversation).get()
        operator = self.as_user(self.operator)
        claim_conversation(context=operator, conversation_id=conversation.pk)
        return_to_queue(context=operator, conversation_id=conversation.pk)
        second = self.executions(conversation).exclude(pk=first.pk).get()
        self.assertEqual(self.status(second), ("PENDING", ""))
        self.assertGreater(second.scheduled_for, first.scheduled_for)
        # Опоздавшая работа по прежнему ожиданию не оповещает о новом.
        self.deliver(first)
        self.assertFalse(self.notices(self.key).exists())
        self.deliver(second)
        self.assertEqual(self.notified(self.key), {self.owner.user_id})

    def test_availability_counts_only_under_the_explicit_condition(self) -> None:
        recipients = ["CONVERSATION_GROUP", "MANAGEMENT"]
        self.enable(NOTICE, delay_minutes=7, recipients=recipients)
        everyone = {self.operator.user_id, self.colleague.user_id, self.owner.user_id}
        # Без условия рабочий статус не спрашивают: все сейчас «недоступны».
        conversation = self.receive("plain", user="plain")
        self.deliver(self.executions(conversation).get())
        self.assertEqual(self.notified(self.key), everyone)

        self.notices(self.key).delete()
        self.enable(NOTICE, conditions={"availableOnly": True})
        nobody = self.receive("nobody", user="nobody")
        execution = self.executions(nobody).get()
        self.deliver(execution)
        self.assertEqual(self.status(execution), ("SKIPPED", "no_recipients"))
        self.assertFalse(self.notices(self.key).exists())

        self.make_ready(self.colleague)
        ready = self.receive("ready", user="ready")
        execution = self.executions(ready).get()
        self.deliver(execution)
        self.assertEqual(self.notified(self.key), {self.colleague.user_id})
        execution.refresh_from_db()
        self.assertEqual(execution.recipient_user_ids, [self.colleague.user_id])

    def test_blocked_and_removed_employees_are_not_called(self) -> None:
        self.enable(
            NOTICE, delay_minutes=7, recipients=["CONVERSATION_GROUP", "GROUP_SUPERVISORS"]
        )
        conversation = self.receive("first")
        # Доступ считается в момент исполнения, а не постановки.
        OrganizationMembership.objects.filter(pk=self.operator.pk).update(blocked_at=timezone.now())
        self.colleague.group_links.all().delete()
        self.lead.supervision_links.all().delete()
        execution = self.executions(conversation).get()
        self.deliver(execution)
        self.assertEqual(self.status(execution), ("SKIPPED", "no_recipients"))
        self.assertFalse(self.notices(self.key).exists())
