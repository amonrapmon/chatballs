"""Уведомление доезжает до открытого приложения событием, а не опросом.

Событие адресное: в личную группу каждого получателя. Организация целиком не
годится — сотрудник видит не все уведомления, и рассылка на всех означала бы,
что о чужих он как минимум узнаёт.
"""

from unittest import mock

from django.test import TestCase

from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.identity.group_models import EmployeeGroup, EmployeeGroupMember
from chatballs.identity.models import (
    EmployeeRole,
    HumanUser,
    Organization,
    OrganizationMembership,
)
from chatballs.notifications.delivery import NOTIFICATION_CREATED
from chatballs.notifications.models import NotificationAudience, NotificationType
from chatballs.notifications.realtime import user_group
from chatballs.notifications.services import notify
from chatballs.testing import tenant_context_for


class NotificationFanoutTests(TestCase):
    def setUp(self) -> None:
        self.organization = Organization.objects.create(name="Example", slug="notify-fanout")
        self.support = EmployeeGroup.objects.create(
            organization=self.organization, name="Поддержка"
        )
        self.owner = self._employee("owner@fanout.test", EmployeeRole.OWNER)
        self.insider = self._employee("insider@fanout.test", EmployeeRole.EMPLOYEE)
        self.outsider = self._employee("outsider@fanout.test", EmployeeRole.EMPLOYEE)
        EmployeeGroupMember.objects.create(
            organization=self.organization, group=self.support, employee=self.insider
        )
        self.context = tenant_context_for(self.owner.user, self.organization)

    def _employee(self, email: str, role: str) -> OrganizationMembership:
        user = HumanUser.objects.create_user(email=email, password="Password-123")
        return OrganizationMembership.objects.create(
            user=user, organization=self.organization, role=role, position_title="Specialist"
        )

    def _dispatch_last_event(self) -> list[str]:
        """Разбирает событие из outbox и возвращает группы, в которые ушёл оклик."""
        event = OutboxEvent.objects.filter(event_type=NOTIFICATION_CREATED).latest("created_at")
        with mock.patch("chatballs.notifications.realtime.publish") as publish:
            dispatch(event)
        return [call.args[0] for call in publish.call_args_list]

    def test_event_goes_to_personal_groups_of_recipients_only(self) -> None:
        notify(
            context=self.context,
            type=NotificationType.OPERATOR_REQUESTED,
            audience=NotificationAudience.OPERATORS,
            audience_group=self.support,
            title="Нужен оператор",
        )
        groups = self._dispatch_last_event()
        self.assertEqual(
            set(groups),
            {user_group(self.owner.user_id), user_group(self.insider.user_id)},
        )
        self.assertNotIn(user_group(self.outsider.user_id), groups)

    def test_event_carries_no_content(self) -> None:
        """В канал уходит только повод перезапросить: ни текста, ни номера."""
        notify(
            context=self.context,
            type=NotificationType.OPERATOR_REQUESTED,
            audience=NotificationAudience.OPERATORS,
            title="Нужен оператор",
            body="Клиент ждёт ответа",
        )
        event = OutboxEvent.objects.filter(event_type=NOTIFICATION_CREATED).latest("created_at")
        with mock.patch("chatballs.notifications.realtime.publish") as publish:
            dispatch(event)
        for call in publish.call_args_list:
            self.assertEqual(call.args[1], {"type": "notifications.changed"})

    def test_personal_notification_reaches_only_its_recipient(self) -> None:
        notify(
            context=self.context,
            type=NotificationType.DIALOG_NEW_MESSAGE,
            audience=NotificationAudience.USER,
            recipient_user=self.outsider.user,
            title="Новое сообщение",
        )
        self.assertEqual(self._dispatch_last_event(), [user_group(self.outsider.user_id)])
