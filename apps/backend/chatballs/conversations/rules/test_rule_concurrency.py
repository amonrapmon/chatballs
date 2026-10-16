"""Гонки исполнителя: настоящие транзакции в параллельных соединениях."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from django.db import close_old_connections
from django.test import TransactionTestCase

from chatballs.conversations.models import Conversation, SystemEvent
from chatballs.conversations.rules.rule_test_base import RuleScene
from chatballs.conversations.services import assign_operator, claim_conversation
from chatballs.events.handlers import dispatch
from chatballs.notifications.models import Notification
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import tenant_context_for


def in_own_connection(function):
    def run(*args):
        close_old_connections()
        try:
            return function(*args)
        finally:
            close_old_connections()
    return run


class RuleConcurrencyTests(RuleScene, TransactionTestCase):
    slug = "concurrent-rules"

    def effects(self) -> tuple[int, int, int]:
        return (
            self.conversation.domain_events.filter(
                event_type="TRANSFERRED", responsible_id__isnull=True
            ).count(),
            self.conversation.messages.filter(system_event=SystemEvent.ASSIGNMENT_EXPIRED).count(),
            Notification.objects.filter(title_key="notifications.assignment_expired").count(),
        )

    def test_two_workers_perform_one_return(self) -> None:
        execution = self.assign(self.operator)
        event = self.due_events(execution).get()
        barrier = Barrier(2)

        @in_own_connection
        def work() -> None:
            barrier.wait(timeout=10)
            dispatch(event)

        with ThreadPoolExecutor(max_workers=2) as pool:
            for future in [pool.submit(work) for _ in range(2)]:
                future.result(timeout=30)
        self.conversation.refresh_from_db()
        self.assertIsNone(self.conversation.assigned_operator_id)
        self.assertEqual(self.effects(), (1, 1, 1))
        execution.refresh_from_db()
        self.assertEqual(execution.status, "EXECUTED")

    def _race_worker_against(self, change) -> None:
        """Воркер ждёт блокировку диалога, пока идёт `change`, и видит его итог."""
        self.execution = self.assign(self.operator)
        event = self.due_events(self.execution).get()
        locked, release = Event(), Event()

        @in_own_connection
        def operator_side() -> None:
            with tenant_atomic(self.context):
                Conversation.objects.select_for_update().get(pk=self.conversation.pk)
                locked.set()
                release.wait(timeout=10)
                change()

        @in_own_connection
        def worker_side() -> None:
            locked.wait(timeout=10)
            dispatch(event)

        with ThreadPoolExecutor(max_workers=2) as pool:
            operator = pool.submit(operator_side)
            worker = pool.submit(worker_side)
            locked.wait(timeout=10)
            # Воркер уже стоит на блокировке диалога, когда операция завершается.
            self.assertFalse(worker.done())
            release.set()
            operator.result(timeout=30)
            worker.result(timeout=30)
        self.conversation.refresh_from_db()
        self.execution.refresh_from_db()

    def test_acceptance_racing_the_worker_keeps_the_assignee(self) -> None:
        self._race_worker_against(lambda: claim_conversation(
            context=tenant_context_for(self.operator.user, self.organization),
            conversation_id=self.conversation.pk,
        ))
        self.assertEqual(self.conversation.assigned_operator_id, self.operator.user_id)
        self.assertEqual(self.conversation.control_mode, "HUMAN")
        self.assertEqual(self.effects(), (0, 0, 0))
        self.assertEqual(
            (self.execution.status, self.execution.reason), ("SKIPPED", "assignment_accepted")
        )

    def test_reassignment_racing_the_worker_keeps_the_new_assignee(self) -> None:
        self._race_worker_against(lambda: assign_operator(
            context=self.context, conversation_id=self.conversation.pk,
            assignee=self.colleague.user,
        ))
        self.assertEqual(self.conversation.assigned_operator_id, self.colleague.user_id)
        self.assertEqual(self.effects(), (0, 0, 0))
        self.assertEqual(
            (self.execution.status, self.execution.reason), ("SKIPPED", "assignment_replaced")
        )
        self.assertEqual(self.executions().filter(status="PENDING").count(), 1)
