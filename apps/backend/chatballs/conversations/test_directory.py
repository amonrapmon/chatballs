"""Справочник выбора ответственного: ограниченная выдача, поиск и присутствие."""

from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from chatballs.channels.models import Channel
from chatballs.conversations.chat_extras_views import DIRECTORY_LIMIT
from chatballs.conversations.models import Contact, Conversation, LifecycleState
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import (
    EmployeeRole,
    HumanUser,
    Organization,
    OrganizationMembership,
)
from chatballs.presence import touch
from chatballs.testing import TenantAPIClient as APIClient


class ConversationDirectoryTests(TestCase):
    def setUp(self) -> None:
        bootstrap_owner(email="owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        for index in range(DIRECTORY_LIMIT + 10):
            user = HumanUser.objects.create_user(
                email=f"member{index:03d}@example.com",
                password="Password-123",
                full_name=f"Сотрудник {index:03d}",
            )
            OrganizationMembership.objects.create(
                user=user,
                organization=self.organization,
                role=EmployeeRole.EMPLOYEE,
                position_title="Оператор",
            )
        self.client = APIClient()
        self.client.login(username="owner@example.com", password="temporary-password")

    def _directory(self, query: str = "") -> dict:
        response = self.client.get(f"/api/v1/conversations/directory/{query}")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_employees_are_bounded_and_report_the_rest(self) -> None:
        payload = self._directory()
        self.assertEqual(len(payload["employees"]), DIRECTORY_LIMIT)
        self.assertTrue(payload["hasMoreEmployees"])

    def test_search_finds_colleague_outside_the_first_rows(self) -> None:
        # Именно ради этого случая в выборе и появляется строка поиска.
        payload = self._directory("?q=Сотрудник 057")
        self.assertEqual([item["name"] for item in payload["employees"]], ["Сотрудник 057"])
        self.assertFalse(payload["hasMoreEmployees"])

    def test_search_matches_email(self) -> None:
        payload = self._directory("?q=member042@")
        self.assertEqual(len(payload["employees"]), 1)

    def test_groups_are_returned_as_before(self) -> None:
        self.assertIn("groups", self._directory())


class DirectoryPresenceTests(TestCase):
    """Присутствие и загрузка в выборе ответственного (макет Q5).

    Назначить отсутствующего можно — признак ничего не запрещает; он лишь
    отвечает на вопрос «кто сейчас за рабочим местом».
    """

    def setUp(self) -> None:
        cache.clear()
        self.organization = Organization.objects.create(name="Example", slug="directory-presence")
        self.owner = self._employee("owner@dir.test", EmployeeRole.OWNER)
        self.away = self._employee("away@dir.test", EmployeeRole.EMPLOYEE)
        self.client = APIClient()
        self.client.force_authenticate(self.owner.user)

    def _employee(self, email: str, role: str) -> OrganizationMembership:
        user = HumanUser.objects.create_user(email=email, password="Password-123")
        return OrganizationMembership.objects.create(
            user=user, organization=self.organization, role=role, position_title="Specialist"
        )

    def _rows(self) -> dict[int, dict]:
        response = self.client.get("/api/v1/conversations/directory/")
        self.assertEqual(response.status_code, 200)
        return {row["id"]: row for row in response.json()["employees"]}

    def test_presence_is_reported_for_whoever_is_in_the_app(self) -> None:
        touch(self.organization.id, self.owner.user_id)
        rows = self._rows()
        self.assertTrue(rows[self.owner.user_id]["online"])
        self.assertIsNotNone(rows[self.owner.user_id]["lastSeenAt"])
        self.assertFalse(rows[self.away.user_id]["online"])
        self.assertIsNone(rows[self.away.user_id]["lastSeenAt"])

    def test_long_gone_employee_is_not_online_but_remembered(self) -> None:
        with mock.patch(
            "chatballs.presence.timezone.now",
            return_value=timezone.now() - timedelta(minutes=25),
        ):
            touch(self.organization.id, self.away.user_id)
        row = self._rows()[self.away.user_id]
        self.assertFalse(row["online"])
        self.assertIsNotNone(row["lastSeenAt"])

    def test_load_counts_only_open_dialogs_of_that_person(self) -> None:
        channel = Channel.objects.create(
            organization=self.organization, code="dir-presence", name="Канал"
        )
        contact = Contact.objects.create(organization=self.organization, name="Клиент")
        for lifecycle in (LifecycleState.OPEN, LifecycleState.OPEN, LifecycleState.CLOSED):
            Conversation.objects.create(
                organization=self.organization,
                channel=channel,
                contact=contact,
                lifecycle=lifecycle,
                assigned_operator=self.owner.user,
            )
        rows = self._rows()
        self.assertEqual(rows[self.owner.user_id]["openDialogs"], 2)
        self.assertEqual(rows[self.away.user_id]["openDialogs"], 0)
