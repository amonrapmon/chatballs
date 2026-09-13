"""Сроки очереди через API (макет Q2).

До этого пороги правились только в служебной админке — то есть де-факто никем.
"""

from django.test import TestCase

from chatballs.conversations.queue_models import QueueEscalationPolicy
from chatballs.identity.models import (
    EmployeeRole,
    HumanUser,
    Organization,
    OrganizationMembership,
)
from chatballs.testing import TenantAPIClient as APIClient

URL = "/api/v1/conversations/queue-policy/"


class QueuePolicyApiTests(TestCase):
    def setUp(self) -> None:
        self.organization = Organization.objects.create(name="Example", slug="queue-policy")
        self.owner = self._employee("owner@policy.test", EmployeeRole.OWNER)
        self.operator = self._employee("operator@policy.test", EmployeeRole.EMPLOYEE)
        self.client = APIClient()
        self.client.force_authenticate(self.owner.user)

    def _employee(self, email: str, role: str) -> OrganizationMembership:
        user = HumanUser.objects.create_user(email=email, password="Password-123")
        return OrganizationMembership.objects.create(
            user=user, organization=self.organization, role=role, position_title="Specialist"
        )

    def test_first_read_returns_usual_delays(self) -> None:
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["remind_after_minutes"], 5)
        self.assertEqual(payload["assignment_timeout_minutes"], 10)
        self.assertEqual(payload["defaults"], payload["defaults"] | {"widen_after_minutes": 15})
        self.assertIsNone(payload["updatedAt"])

    def test_saving_remembers_who_and_when(self) -> None:
        response = self.client.patch(URL, {"remind_after_minutes": 3}, format="json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["remind_after_minutes"], 3)
        self.assertEqual(payload["updatedBy"], self.owner.user.full_name or self.owner.user.email)
        self.assertIsNotNone(payload["updatedAt"])
        self.assertEqual(QueueEscalationPolicy.objects.get().remind_after_minutes, 3)

    def test_nonsense_values_are_refused(self) -> None:
        for value in (0, -5, 10000, "быстро", True):
            with self.subTest(value=value):
                response = self.client.patch(URL, {"widen_after_minutes": value}, format="json")
                self.assertEqual(response.status_code, 400)
        self.assertEqual(QueueEscalationPolicy.objects.get().widen_after_minutes, 15)

    def test_operator_reads_but_does_not_change(self) -> None:
        self.client.force_authenticate(self.operator.user)
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(
            self.client.patch(URL, {"remind_after_minutes": 1}, format="json").status_code, 403
        )
