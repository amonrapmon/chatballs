"""Уведомление о диалоге видно тем же, кому виден сам диалог.

Регрессия: уведомления фильтровались только правом «видеть диалоги», а диалоги —
ещё и группой (ADR-CHATBALLS-0043 §4). Оператор чужой группы получал оклик с
именем клиента и куском переписки, а открыть диалог не мог.
"""

from django.test import TestCase

from chatballs.identity.group_models import EmployeeGroup, EmployeeGroupMember
from chatballs.identity.models import (
    EmployeeRole,
    HumanUser,
    Organization,
    OrganizationMembership,
)
from chatballs.notifications.models import NotificationAudience, NotificationType
from chatballs.notifications.recipients import recipient_user_ids
from chatballs.notifications.selectors import visible_for
from chatballs.notifications.services import notify
from chatballs.testing import tenant_context_for


class NotificationGroupVisibilityTests(TestCase):
    def setUp(self) -> None:
        self.organization = Organization.objects.create(name="Example", slug="notify-groups")
        self.support = EmployeeGroup.objects.create(
            organization=self.organization, name="Поддержка"
        )
        self.sales = EmployeeGroup.objects.create(organization=self.organization, name="Продажи")
        self.owner = self._employee("owner@notify.test", EmployeeRole.OWNER)
        self.insider = self._employee("insider@notify.test", EmployeeRole.EMPLOYEE)
        self.outsider = self._employee("outsider@notify.test", EmployeeRole.EMPLOYEE)
        EmployeeGroupMember.objects.create(
            organization=self.organization, group=self.support, employee=self.insider
        )
        EmployeeGroupMember.objects.create(
            organization=self.organization, group=self.sales, employee=self.outsider
        )
        self.context = tenant_context_for(self.owner.user, self.organization)

    def _employee(self, email: str, role: str) -> OrganizationMembership:
        user = HumanUser.objects.create_user(email=email, password="Password-123")
        return OrganizationMembership.objects.create(
            user=user, organization=self.organization, role=role, position_title="Specialist"
        )

    def _visible_ids(self, membership: OrganizationMembership) -> set[int]:
        context = tenant_context_for(membership.user, self.organization)
        return set(visible_for(context).values_list("id", flat=True))

    def _waiting(self, group: EmployeeGroup | None):
        return notify(
            context=self.context,
            type=NotificationType.OPERATOR_REQUESTED,
            audience=NotificationAudience.OPERATORS,
            audience_group=group,
            title="Нужен оператор",
        )

    def test_group_notification_reaches_only_that_group_and_management(self) -> None:
        notification = self._waiting(self.support)
        self.assertIn(notification.id, self._visible_ids(self.insider))
        self.assertNotIn(notification.id, self._visible_ids(self.outsider))
        self.assertIn(notification.id, self._visible_ids(self.owner))

    def test_notification_without_group_stays_visible_to_everyone(self) -> None:
        notification = self._waiting(None)
        for membership in (self.insider, self.outsider, self.owner):
            self.assertIn(notification.id, self._visible_ids(membership))

    def test_recipients_match_what_the_list_shows(self) -> None:
        """Доставка и список обязаны отвечать одинаково.

        Иначе уведомление уходит в мессенджер тому, кто потом не находит его в
        приложении, или наоборот.
        """
        for group in (self.support, None):
            notification = self._waiting(group)
            delivered = set(recipient_user_ids(notification))
            listed = {
                membership.user_id
                for membership in (self.owner, self.insider, self.outsider)
                if notification.id in self._visible_ids(membership)
            }
            self.assertEqual(delivered, listed)
