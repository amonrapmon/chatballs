"""Удаление диалога: право, полнота и последствия для виджета.

Решение владельца 2026-09-14: «удалить» означает удалить, а не отправить в
архив. Удалённый диалог не принимает сообщений, не окликает уведомлениями и
обнуляет переписку в виджете клиента.
"""

import json

from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.models import (
    Contact,
    Conversation,
    Message,
    MessageAuthor,
)
from chatballs.identity.group_models import EmployeeGroup, EmployeeGroupMember
from chatballs.identity.models import (
    EmployeeRole,
    HumanUser,
    Organization,
    OrganizationMembership,
)
from chatballs.notifications.models import Notification, NotificationType
from chatballs.testing import TenantAPIClient as APIClient


class ConversationDeleteTests(TestCase):
    def setUp(self) -> None:
        self.organization = Organization.objects.create(name="Chat", slug="chat-delete")
        self.owner = self._member("owner@delete.test", EmployeeRole.OWNER)
        self.employee = self._member("employee@delete.test", EmployeeRole.EMPLOYEE)
        group = EmployeeGroup.objects.create(
            organization=self.organization, name="Операторы"
        )
        EmployeeGroupMember.objects.create(
            organization=self.organization, group=group, employee=self.employee
        )
        self.channel = Channel.objects.create(
            organization=self.organization, code="line", name="Линия"
        )
        contact = Contact.objects.create(organization=self.organization, name="Иван")
        self.conversation = Conversation.objects.create(
            organization=self.organization, channel=self.channel, contact=contact
        )
        self.message = Message.objects.create(
            conversation=self.conversation,
            author_type=MessageAuthor.CONTACT,
            text="Здравствуйте",
        )
        self.owner_client = APIClient()
        self.owner_client.force_authenticate(self.owner.user)
        self.employee_client = APIClient()
        self.employee_client.force_authenticate(self.employee.user)

    def _member(self, email: str, role: str) -> OrganizationMembership:
        user = HumanUser.objects.create_user(email=email, password="Password-123")
        return OrganizationMembership.objects.create(
            user=user,
            organization=self.organization,
            role=role,
            position_title="Specialist",
        )

    def _url(self) -> str:
        return f"/api/v1/conversations/{self.conversation.id}/"

    def test_operator_cannot_delete(self) -> None:
        response = self.employee_client.delete(self._url())
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Conversation.objects.filter(id=self.conversation.id).exists())

    def test_owner_deletes_conversation_with_history(self) -> None:
        response = self.owner_client.delete(self._url())
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Conversation.objects.filter(id=self.conversation.id).exists())
        self.assertFalse(Message.objects.filter(id=self.message.id).exists())

    def test_notifications_about_conversation_are_gone(self) -> None:
        Notification.objects.create(
            organization=self.organization,
            type=NotificationType.NEW_DIALOG,
            title="Новый диалог",
            target_route="chat",
            target_id=str(self.conversation.id),
            source_type="Conversation",
            source_id=str(self.conversation.id),
        )
        self.owner_client.delete(self._url())
        self.assertEqual(Notification.objects.count(), 0)

    def test_deleted_conversation_cannot_be_written_to(self) -> None:
        self.owner_client.delete(self._url())
        response = self.owner_client.post(
            f"{self._url()}messages/",
            data=json.dumps({"text": "ещё раз"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_missing_conversation_is_not_found(self) -> None:
        self.owner_client.delete(self._url())
        self.assertEqual(self.owner_client.delete(self._url()).status_code, 404)
