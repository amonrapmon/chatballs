"""Эскалация ждущих диалогов и личная очередь назначенного.

Регрессия, ради которой всё это заведено: про ждущий диалог операторов окликали
ровно один раз, и дальше суточный dedup гарантировал тишину. Назначение при этом
молча писало внешний ключ — назначенный не узнавал, а из общей очереди диалог
уже ушёл.
"""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from chatballs.channels.models import Channel
from chatballs.conversations.escalation import sweep_waiting_conversations
from chatballs.conversations.models import (
    Contact,
    ControlMode,
    Conversation,
    ExpectedResponder,
    LifecycleState,
    SystemEvent,
)
from chatballs.conversations.queue_models import policy_for
from chatballs.conversations.services import assign_operator
from chatballs.identity.group_models import EmployeeGroup, EmployeeGroupMember
from chatballs.identity.models import (
    EmployeeRole,
    HumanUser,
    Organization,
    OrganizationMembership,
)
from chatballs.notifications.models import Notification, NotificationAudience
from chatballs.presence import touch
from chatballs.testing import tenant_context_for


class QueueTestBase(TestCase):
    def setUp(self) -> None:
        self.organization = Organization.objects.create(name="Example", slug="queue-escalation")
        self.support = EmployeeGroup.objects.create(
            organization=self.organization, name="Поддержка"
        )
        self.owner = self._employee("owner@queue.test", EmployeeRole.OWNER)
        self.operator = self._employee("operator@queue.test", EmployeeRole.EMPLOYEE)
        EmployeeGroupMember.objects.create(
            organization=self.organization, group=self.support, employee=self.operator
        )
        self.context = tenant_context_for(self.owner.user, self.organization)
        self.policy = policy_for(self.organization)
        self.channel = Channel.objects.create(
            organization=self.organization, group=self.support, code="esc", name="Очередь"
        )
        self.conversation = self._waiting_conversation()
        # Обычный случай: смена на месте. Пустую смену проверяет
        # PresenceEscalationTests, и она её задаёт явно.
        cache.clear()
        touch(self.organization.id, self.operator.user_id)

    def _employee(self, email: str, role: str) -> OrganizationMembership:
        user = HumanUser.objects.create_user(email=email, password="Password-123")
        return OrganizationMembership.objects.create(
            user=user, organization=self.organization, role=role, position_title="Specialist"
        )

    def _waiting_conversation(self) -> Conversation:
        contact = Contact.objects.create(organization=self.organization, name="Клиент")
        return Conversation.objects.create(
            organization=self.organization,
            channel=self.channel,
            group=self.support,
            contact=contact,
            lifecycle=LifecycleState.OPEN,
            control_mode=ControlMode.PAUSED,
            expected_responder=ExpectedResponder.OPERATOR,
            waiting_since=timezone.now(),
        )

    def _wait_for(self, minutes: int) -> None:
        Conversation.objects.filter(pk=self.conversation.pk).update(
            waiting_since=timezone.now() - timedelta(minutes=minutes)
        )

    def _dedup_keys(self) -> set[str]:
        return set(
            Notification.objects.filter(organization=self.organization).values_list(
                "dedup_key", flat=True
            )
        )



class QueueEscalationTests(QueueTestBase):
    def test_fresh_dialog_is_not_escalated(self) -> None:
        self.assertEqual(sweep_waiting_conversations(self.context), 0)
        self.assertEqual(self._dedup_keys(), set())

    def test_reminder_goes_to_the_group_of_the_dialog(self) -> None:
        self._wait_for(self.policy.remind_after_minutes + 1)
        self.assertEqual(sweep_waiting_conversations(self.context), 1)
        reminder = Notification.objects.get(dedup_key=f"waiting:{self.conversation.id}:remind")
        self.assertEqual(reminder.audience, NotificationAudience.OPERATORS)
        self.assertEqual(reminder.audience_group_id, self.support.id)

    def test_circle_widens_beyond_the_group(self) -> None:
        self._wait_for(self.policy.widen_after_minutes + 1)
        sweep_waiting_conversations(self.context)
        widened = Notification.objects.get(dedup_key=f"waiting:{self.conversation.id}:widen")
        self.assertIsNone(widened.audience_group_id)

    def test_management_is_called_last(self) -> None:
        self._wait_for(self.policy.escalate_after_minutes + 1)
        sweep_waiting_conversations(self.context)
        management = Notification.objects.filter(
            dedup_key__startswith=f"waiting:{self.conversation.id}:management"
        )
        self.assertEqual(
            {item.recipient_user_id for item in management}, {self.owner.user_id}
        )

    def test_second_sweep_does_not_repeat_itself(self) -> None:
        self._wait_for(self.policy.escalate_after_minutes + 1)
        first = sweep_waiting_conversations(self.context)
        second = sweep_waiting_conversations(self.context)
        self.assertGreater(first, 0)
        self.assertEqual(second, 0)

    def test_assigned_dialog_is_not_escalated_to_everyone(self) -> None:
        assign_operator(
            context=self.context,
            conversation_id=self.conversation.id,
            assignee=self.operator.user,
        )
        self._wait_for(self.policy.escalate_after_minutes + 1)
        sweep_waiting_conversations(self.context)
        self.assertEqual(
            {key for key in self._dedup_keys() if key.startswith("waiting:")}, set()
        )


class AssignmentTests(QueueTestBase):
    def test_assignment_notifies_the_assignee_and_writes_history(self) -> None:
        assign_operator(
            context=self.context,
            conversation_id=self.conversation.id,
            assignee=self.operator.user,
        )
        notification = Notification.objects.get(
            dedup_key=f"assign:{self.conversation.id}:{self.operator.user_id}"
        )
        self.assertEqual(notification.audience, NotificationAudience.USER)
        self.assertEqual(notification.recipient_user_id, self.operator.user_id)
        self.assertEqual(
            list(self.conversation.messages.values_list("system_event", flat=True)),
            [SystemEvent.ASSIGNED_TO],
        )

    def test_assigning_to_yourself_does_not_ping_you(self) -> None:
        assign_operator(
            context=self.context,
            conversation_id=self.conversation.id,
            assignee=self.owner.user,
        )
        self.assertFalse(
            Notification.objects.filter(
                dedup_key=f"assign:{self.conversation.id}:{self.owner.user_id}"
            ).exists()
        )

    def test_unclaimed_assignment_returns_the_dialog_to_the_queue(self) -> None:
        assign_operator(
            context=self.context,
            conversation_id=self.conversation.id,
            assignee=self.operator.user,
        )
        Conversation.objects.filter(pk=self.conversation.pk).update(
            assigned_at=timezone.now()
            - timedelta(minutes=self.policy.assignment_timeout_minutes + 1)
        )
        sweep_waiting_conversations(self.context)

        self.conversation.refresh_from_db()
        self.assertIsNone(self.conversation.assigned_operator_id)
        self.assertIsNone(self.conversation.assigned_at)
        # Ожидание не обнулилось: клиент ждёт с того же момента, что и ждал.
        self.assertIsNotNone(self.conversation.waiting_since)
        self.assertIn(
            SystemEvent.ASSIGNMENT_EXPIRED,
            set(self.conversation.messages.values_list("system_event", flat=True)),
        )


class PresenceEscalationTests(QueueTestBase):
    """Присутствие сокращает ожидание, но ничего не запрещает."""

    def setUp(self) -> None:
        super().setUp()
        # Начинаем с пустой смены: за рабочим местом нет никого.
        cache.clear()

    def test_circle_widens_at_the_first_threshold_when_nobody_is_online(self) -> None:
        self._wait_for(self.policy.remind_after_minutes + 1)
        sweep_waiting_conversations(self.context)
        self.assertTrue(
            Notification.objects.filter(
                dedup_key=f"waiting:{self.conversation.id}:widen"
            ).exists()
        )

    def test_present_operator_keeps_the_second_threshold(self) -> None:
        touch(self.organization.id, self.operator.user_id)
        self._wait_for(self.policy.remind_after_minutes + 1)
        sweep_waiting_conversations(self.context)
        # Напомнили группе, но круг не расширили: в группе есть кому ответить.
        self.assertTrue(
            Notification.objects.filter(
                dedup_key=f"waiting:{self.conversation.id}:remind"
            ).exists()
        )
        self.assertFalse(
            Notification.objects.filter(
                dedup_key=f"waiting:{self.conversation.id}:widen"
            ).exists()
        )

    def test_presence_never_delays_the_wider_circle(self) -> None:
        touch(self.organization.id, self.operator.user_id)
        self._wait_for(self.policy.widen_after_minutes + 1)
        sweep_waiting_conversations(self.context)
        self.assertTrue(
            Notification.objects.filter(
                dedup_key=f"waiting:{self.conversation.id}:widen"
            ).exists()
        )

    def test_operator_of_another_group_does_not_count_as_present(self) -> None:
        outsider = self._employee("outsider@queue.test", EmployeeRole.EMPLOYEE)
        touch(self.organization.id, outsider.user_id)
        self._wait_for(self.policy.remind_after_minutes + 1)
        sweep_waiting_conversations(self.context)
        self.assertTrue(
            Notification.objects.filter(
                dedup_key=f"waiting:{self.conversation.id}:widen"
            ).exists()
        )
