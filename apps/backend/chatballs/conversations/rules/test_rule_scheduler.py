"""Планирование, отмена и повтор отложенного действия правила."""

from datetime import timedelta
from unittest import mock

from django.db import transaction
from django.test import TestCase

from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.models import Conversation
from chatballs.conversations.rules import executor
from chatballs.conversations.rules.models import HandlingRule, HandlingRuleKind
from chatballs.conversations.rules.rule_test_base import RuleScene
from chatballs.conversations.rules.settings import rule_for, update_rule
from chatballs.conversations.services import claim_conversation, close_conversation
from chatballs.conversations.transports.base import InboundMessage
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.events.services import MAX_OUTBOX_ATTEMPTS, claim_next_outbox_event
from chatballs.testing import tenant_context_for

RETURN = HandlingRuleKind.ASSIGNMENT_RETURN


class RuleSchedulerTests(RuleScene, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.rule = rule_for(self.organization.pk, RETURN)

    def status(self, execution) -> tuple[str, str]:
        execution.refresh_from_db()
        return execution.status, execution.reason

    def test_assignment_plans_the_return_from_its_own_fact(self) -> None:
        execution = self.assign(self.operator)
        fact = self.conversation.domain_events.get(event_type="ASSIGNED")
        self.assertEqual(
            (execution.source_event_id, execution.rule_id, execution.rule_version,
             execution.status, execution.finished_at),
            (fact.pk, self.rule.pk, 1, "PENDING", None),
        )
        self.assertEqual(
            execution.scheduled_for, fact.occurred_at + timedelta(minutes=self.rule.delay_minutes)
        )
        event = self.due_events().get()
        self.assertEqual(
            (event.aggregate_type, event.aggregate_id, event.organization_id, event.actor_kind),
            ("RuleExecution", str(execution.pk), self.organization.pk, "SYSTEM"),
        )
        self.assertEqual(event.next_attempt_at, execution.scheduled_for)
        self.assertEqual(event.payload["executionId"], execution.pk)

    def test_record_and_outbox_event_are_written_together_or_not_at_all(self) -> None:
        with self.assertRaises(RuntimeError), transaction.atomic():
            self.assign(self.operator)
            raise RuntimeError("abort the assignment")
        self.assertEqual((self.executions().count(), self.due_events().count()), (0, 0))
        with mock.patch(
            "chatballs.conversations.rules.scheduler.enqueue_event", side_effect=RuntimeError
        ), self.assertRaises(RuntimeError):
            self.assign(self.operator)
        self.conversation.refresh_from_db()
        # Без события нет ни записи журнала, ни самого назначения.
        self.assertIsNone(self.conversation.assigned_operator_id)
        self.assertEqual((self.executions().count(), self.due_events().count()), (0, 0))

    def test_due_event_waits_for_the_deadline(self) -> None:
        execution = self.assign(self.operator)
        OutboxEvent.objects.exclude(pk=self.due_events().get().pk).delete()
        with mock.patch("chatballs.events.services.OUTBOX_DB", "default"):
            self.assertIsNone(claim_next_outbox_event())
            late = execution.scheduled_for + timedelta(seconds=1)
            with mock.patch("chatballs.events.services.timezone.now", return_value=late):
                self.assertEqual(claim_next_outbox_event().aggregate_id, str(execution.pk))

    def test_repeated_customer_message_does_not_reset_the_deadline(self) -> None:
        inbound = InboundMessage(
            external_id="first", user_id="client", chat_id="client", text="Hello",
            display_name="Client",
        )
        ingest_inbound(self.connection, inbound)
        self.conversation = Conversation.objects.exclude(pk=self.conversation.pk).get()
        waiting_since = self.conversation.waiting_since
        execution = self.assign(self.operator)
        scheduled_for = execution.scheduled_for
        for number in range(2):
            ingest_inbound(self.connection, InboundMessage(
                external_id=f"again-{number}", user_id="client", chat_id="client",
                text="Anyone there?", display_name="Client",
            ))
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.messages.filter(author_type="CONTACT").count(), 3)
        self.assertEqual(self.conversation.waiting_since, waiting_since)
        self.assertEqual(self.executions().get().scheduled_for, scheduled_for)
        self.assertEqual(self.due_events().get().next_attempt_at, scheduled_for)

    def test_new_assignment_has_a_separate_deadline(self) -> None:
        first = self.assign(self.operator)
        second = self.assign(self.colleague)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(self.status(first), ("SKIPPED", "assignment_replaced"))
        self.assertEqual(self.status(second), ("PENDING", ""))
        self.assertGreater(second.scheduled_for, first.scheduled_for)
        self.assertEqual(second.source_event.responsible_id, self.colleague.user_id)

    def test_acceptance_closure_and_release_cancel_the_pending_return(self) -> None:
        operator = tenant_context_for(self.operator.user, self.organization)
        cases = (
            ("assignment_accepted", lambda: claim_conversation(
                context=operator, conversation_id=self.conversation.pk)),
            ("assignment_replaced", lambda: claim_conversation(
                context=self.context, conversation_id=self.conversation.pk)),
            ("assignment_removed", lambda: self.assign(None)),
            ("conversation_not_open", lambda: close_conversation(
                context=self.context, conversation_id=self.conversation.pk)),
        )
        for reason, change in cases:
            with self.subTest(reason=reason), transaction.atomic():
                execution = self.assign(self.operator)
                change()
                self.assertEqual(self.status(execution), ("SKIPPED", reason))
                self.assertIsNotNone(execution.finished_at)
                transaction.set_rollback(True)

    def test_stale_work_is_skipped_with_a_reason_when_its_time_comes(self) -> None:
        cases = (
            ("rule_disabled", lambda: HandlingRule.objects.filter(pk=self.rule.pk).update(enabled=False)),
            ("conversation_not_open", lambda: self._set(lifecycle="CLOSED")),
            ("assignment_removed", lambda: self._set(assigned_operator=None)),
            ("assignment_replaced", lambda: self._set(assigned_operator=self.colleague.user)),
            ("not_waiting", lambda: self._set(control_mode="AI", waiting_since=None)),
        )
        for reason, change in cases:
            with self.subTest(reason=reason), transaction.atomic():
                execution = self.assign(self.operator)
                # Состояние изменилось в обход фактов: проверка в срок — последняя.
                change()
                self.deliver(execution)
                self.assertEqual(self.status(execution), ("SKIPPED", reason))
                self.assertFalse(
                    self.conversation.messages.filter(system_event="ASSIGNMENT_EXPIRED").exists()
                )
                transaction.set_rollback(True)

    def _set(self, **fields) -> None:
        Conversation.objects.filter(pk=self.conversation.pk).update(**fields)

    def test_disabled_rule_cancels_pending_work_and_plans_nothing_new(self) -> None:
        execution = self.assign(self.operator)
        update_rule(context=self.context, kind=RETURN, changes={"enabled": False})
        self.assertEqual(self.status(execution), ("SKIPPED", "rule_disabled"))
        self.deliver(execution)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.operator.user_id)
        self.assign(self.colleague)
        self.assertEqual(list(self.executions()), [execution])
        self.assertEqual(self.due_events().count(), 1)

    def test_changed_delay_moves_pending_work_and_retires_the_old_event(self) -> None:
        execution = self.assign(self.operator)
        old_event = self.due_events().get()
        rule = update_rule(context=self.context, kind=RETURN, changes={"delay_minutes": 45})
        execution.refresh_from_db()
        self.assertEqual(execution.rule_version, rule.version)
        self.assertEqual(
            execution.scheduled_for, execution.source_event.occurred_at + timedelta(minutes=45)
        )
        new_event = self.due_events().exclude(pk=old_event.pk).get()
        self.assertEqual(new_event.next_attempt_at, execution.scheduled_for)
        dispatch(old_event)
        self.assertEqual(self.status(execution), ("PENDING", ""))
        dispatch(new_event)
        self.assertEqual(self.status(execution), ("EXECUTED", ""))

    def test_executor_follows_a_rule_version_it_was_not_planned_with(self) -> None:
        execution = self.assign(self.operator)
        # Настройку поменяли мимо планировщика: исполнитель сверяет версию сам.
        HandlingRule.objects.filter(pk=self.rule.pk).update(delay_minutes=90, version=7)
        self.deliver(execution)
        execution.refresh_from_db()
        self.assertEqual((execution.status, execution.rule_version), ("PENDING", 7))
        self.assertEqual(
            execution.scheduled_for, execution.source_event.occurred_at + timedelta(minutes=90)
        )
        self.assertEqual(
            self.due_events().order_by("-next_attempt_at").first().next_attempt_at,
            execution.scheduled_for,
        )
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.operator.user_id)

    def test_failure_rolls_back_is_retried_and_ends_as_an_error(self) -> None:
        execution = self.assign(self.operator)
        failing = executor.ActionHandler(
            stale_reason=executor.ACTIONS["RETURN_TO_QUEUE"].stale_reason,
            perform=mock.Mock(side_effect=RuntimeError("internal details")),
        )
        with mock.patch.dict(executor.ACTIONS, {"RETURN_TO_QUEUE": failing}):
            for attempt in range(1, MAX_OUTBOX_ATTEMPTS + 1):
                with self.assertRaises(RuntimeError):
                    self.deliver(execution)
                execution.refresh_from_db()
                expected = "FAILED" if attempt == MAX_OUTBOX_ATTEMPTS else "PENDING"
                self.assertEqual((execution.attempts, execution.status), (attempt, expected))
        # В журнале код, а не текст исключения; назначение на месте.
        self.assertEqual(execution.reason, "execution_error")
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.operator.user_id)
        # Окончательная ошибка — тоже исход: позднее событие ничего не делает.
        self.deliver(execution)
        self.assertEqual(self.status(execution), ("FAILED", "execution_error"))
        self.assertFalse(self.conversation.domain_events.filter(event_type="TRANSFERRED").exists())
