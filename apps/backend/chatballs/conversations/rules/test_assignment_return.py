"""Возврат непринятого назначения: в срок, один раз и только пока оно в силе."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from chatballs.conversations.escalation import sweep_waiting_conversations
from chatballs.conversations.models import Conversation, SystemEvent
from chatballs.conversations.rules.models import HandlingRuleKind
from chatballs.conversations.rules.rule_test_base import RuleScene
from chatballs.conversations.rules.settings import update_rule
from chatballs.conversations.services import claim_conversation
from chatballs.events.models import OutboxEvent
from chatballs.notifications.delivery import NOTIFICATION_CREATED
from chatballs.notifications.models import Notification, NotificationAudience
from chatballs.testing import system_tenant_context, tenant_context_for

RETURN = HandlingRuleKind.ASSIGNMENT_RETURN


class AssignmentReturnTests(RuleScene, TestCase):
    def returns(self):
        return self.conversation.domain_events.filter(
            event_type="TRANSFERRED", responsible_id__isnull=True
        )

    def expiry_messages(self):
        return self.conversation.messages.filter(system_event=SystemEvent.ASSIGNMENT_EXPIRED)

    def return_notices(self):
        return Notification.objects.filter(
            organization=self.organization, title_key="notifications.assignment_expired"
        )

    def assigned_to(self) -> int | None:
        self.conversation.refresh_from_db()
        return self.conversation.assigned_operator_id

    def test_unaccepted_assignment_returns_with_a_fact_and_a_notification(self) -> None:
        waiting_since = self.conversation.waiting_since
        execution = self.assign(self.operator)
        self.deliver(execution)

        self.assertIsNone(self.assigned_to())
        self.assertIsNone(self.conversation.assigned_at)
        # Диалог остаётся в общей очереди и ждёт с прежнего момента.
        self.assertEqual(
            (self.conversation.lifecycle, self.conversation.control_mode,
             self.conversation.waiting_since),
            ("OPEN", "PAUSED", waiting_since),
        )
        fact = self.returns().get()
        self.assertEqual((fact.actor_kind, fact.initiated_by_id), ("SYSTEM", None))
        message = self.expiry_messages().get()
        notice = self.return_notices().get()
        self.assertEqual(
            (notice.audience, notice.audience_group_id, notice.target_id),
            (NotificationAudience.OPERATORS, self.group.pk, str(self.conversation.pk)),
        )
        self.assertTrue(
            OutboxEvent.objects.filter(
                event_type=NOTIFICATION_CREATED, aggregate_id=str(notice.pk)
            ).exists()
        )
        execution.refresh_from_db()
        self.assertEqual(
            (execution.status, execution.reason, execution.message_id, execution.notification_id),
            ("EXECUTED", "", message.pk, notice.pk),
        )
        self.assertGreaterEqual(execution.finished_at, execution.created_at)
        self.assertEqual(execution.source_event.responsible_id, self.operator.user_id)

    def test_repeated_delivery_does_not_repeat_the_effect(self) -> None:
        execution = self.assign(self.operator)
        event = self.due_events(execution).get()
        OutboxEvent.objects.create(
            aggregate_type=event.aggregate_type, aggregate_id=event.aggregate_id,
            event_type=event.event_type, payload=event.payload, ownership=event.ownership,
            organization=event.organization, actor_kind=event.actor_kind,
        )
        for _ in range(2):
            self.deliver(execution)
        self.assertEqual(
            (self.returns().count(), self.expiry_messages().count(), self.return_notices().count()),
            (1, 1, 1),
        )

    def test_queue_sweep_neither_returns_nor_plans_twice(self) -> None:
        execution = self.assign(self.operator)
        # Прежний обход снимал назначение по одному лишь времени.
        Conversation.objects.filter(pk=self.conversation.pk).update(
            assigned_at=timezone.now() - timedelta(days=1)
        )
        for _ in range(2):
            self.assertEqual(sweep_waiting_conversations(system_tenant_context(self.organization)), 0)
        self.assertEqual(self.assigned_to(), self.operator.user_id)
        self.assertFalse(self.returns().exists())
        self.assertEqual(list(self.executions()), [execution])
        self.assertEqual(self.due_events().count(), 1)

    def test_sweep_plans_an_assignment_that_has_no_deadline_yet(self) -> None:
        # Назначение сделано до появления правил: срок идёт от его же факта.
        self.assign(self.operator).delete()
        self.due_events().delete()
        sweep_waiting_conversations(system_tenant_context(self.organization))
        execution = self.executions().get()
        fact = self.conversation.domain_events.get(event_type="ASSIGNED")
        self.assertEqual(execution.scheduled_for, fact.occurred_at + timedelta(minutes=10))
        self.deliver(execution)
        self.assertIsNone(self.assigned_to())

    def test_reenabled_rule_resumes_the_assignment_it_skipped(self) -> None:
        execution = self.assign(self.operator)
        update_rule(context=self.context, kind=RETURN, changes={"enabled": False})
        update_rule(context=self.context, kind=RETURN, changes={"enabled": True})
        sweep_waiting_conversations(system_tenant_context(self.organization))
        execution.refresh_from_db()
        self.assertEqual((execution.status, execution.reason, execution.rule_version), ("PENDING", "", 3))
        self.deliver(execution)
        self.assertIsNone(self.assigned_to())
        self.assertEqual(self.returns().count(), 1)

    def test_acceptance_before_the_deadline_prevents_the_return(self) -> None:
        execution = self.assign(self.operator)
        claim_conversation(
            context=tenant_context_for(self.operator.user, self.organization),
            conversation_id=self.conversation.pk,
        )
        self.deliver(execution)
        self.assertEqual(self.assigned_to(), self.operator.user_id)
        self.assertEqual(self.conversation.control_mode, "HUMAN")
        self.assertFalse(self.returns().exists() or self.expiry_messages().exists())
        execution.refresh_from_db()
        self.assertEqual((execution.status, execution.reason), ("SKIPPED", "assignment_accepted"))

    def test_replaced_assignment_survives_the_old_deadline(self) -> None:
        first = self.assign(self.operator)
        second = self.assign(self.colleague)
        self.deliver(first)
        self.assertEqual(self.assigned_to(), self.colleague.user_id)
        self.assertFalse(self.returns().exists())
        second.refresh_from_db()
        self.assertEqual(second.status, "PENDING")

    def test_worker_retry_after_a_return_does_not_remove_the_next_assignee(self) -> None:
        first = self.assign(self.operator)
        self.deliver(first)
        second = self.assign(self.colleague)
        # Воркер повторил уже выполненную работу и работу по прежнему назначению.
        self.deliver(first)
        self.assertEqual(self.assigned_to(), self.colleague.user_id)
        self.assertEqual((self.returns().count(), self.return_notices().count()), (1, 1))
        self.deliver(second)
        self.assertIsNone(self.assigned_to())
        # У нового назначения свой возврат и свой оклик.
        self.assertEqual((self.returns().count(), self.return_notices().count()), (2, 2))

    def test_same_operator_assigned_again_gets_a_new_deadline(self) -> None:
        first = self.assign(self.operator)
        self.assign(None)
        second = self.assign(self.operator)
        self.assertNotEqual(first.pk, second.pk)
        self.deliver(first)
        self.assertEqual(self.assigned_to(), self.operator.user_id)
        self.deliver(second)
        self.assertIsNone(self.assigned_to())
