"""Внешний сервер под реальной ролью backend-app: чужая организация его не видит.

Обычные тесты ходят в базу ролью-владельцем схемы, для которой RLS открыта.
Здесь запросы идут ролью ``chatballs_runtime_app``, как в production.
"""

from __future__ import annotations

from django.db import connection
from django.test import TransactionTestCase

from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import EmployeeRole, HumanUser, Organization, OrganizationMembership
from chatballs.integrations.models import Integration, IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.integrations.tool_testing import PUBLIC_IP, fake_dns
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient, system_tenant_context

SETTINGS = {
    "description": "Статус заказа по номеру",
    "toolName": "get_order_status",
    "method": "GET",
    "url": "https://shop.example.test/api/orders/{order_number}",
    "parameters": [{"name": "order_number", "type": "string", "location": "path"}],
    "headers": [{"name": "Authorization", "secret": True, "value": "Bearer shop-secret-token"}],
}


class ExternalServerRuntimeRoleTests(TransactionTestCase):
    def setUp(self) -> None:
        fake_dns(self, {"shop.example.test": [PUBLIC_IP]})
        self.owner = bootstrap_owner(email="rls-server@example.com", password="temporary-password").owner
        self.organization = Organization.objects.get(slug="demo")
        self.server = create_integration(
            context=system_tenant_context(self.organization),
            data=IntegrationInput(provider=IntegrationProvider.HTTP, name="Статус заказа", external=SETTINGS),
        )
        self.other = Organization.objects.create(name="Other", slug="rls-server-other")
        self.other_owner = HumanUser.objects.create_user(email="rls-server-other@example.com")
        OrganizationMembership.objects.create(
            organization=self.other, user=self.other_owner, role=EmployeeRole.OWNER, position_title="Owner"
        )

    def _as_app_role(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE chatballs_runtime_app")
        try:
            return request()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")

    def _client(self, user: HumanUser) -> TenantAPIClient:
        client = TenantAPIClient()
        client.force_authenticate(user)
        return client

    def _url(self, organization: Organization, suffix: str = "") -> str:
        return f"/api/v1/organizations/{organization.public_id}/integrations/{suffix}"

    def test_owner_organization_works_with_the_server_under_app_role(self) -> None:
        client = self._client(self.owner)

        listed = self._as_app_role(lambda: client.get(self._url(self.organization)))
        updated = self._as_app_role(
            lambda: client.patch(
                self._url(self.organization, f"{self.server.id}/"), {"isActive": False}, format="json"
            )
        )

        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual([item["id"] for item in listed.json()["items"]], [self.server.id])
        self.assertEqual(updated.status_code, 200, updated.content)

    def test_foreign_organization_cannot_reach_the_server_under_app_role(self) -> None:
        client = self._client(self.other_owner)
        detail = self._url(self.other, f"{self.server.id}/")

        listed = self._as_app_role(lambda: client.get(self._url(self.other)))
        patched = self._as_app_role(lambda: client.patch(detail, {"isActive": False}, format="json"))
        deleted = self._as_app_role(lambda: client.delete(detail))

        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(listed.json()["items"], [])
        self.assertEqual(patched.status_code, 404)
        self.assertEqual(deleted.status_code, 404)
        self.server.refresh_from_db()
        self.assertTrue(self.server.is_active)

    def test_foreign_tenant_reads_no_rows_and_no_secret_headers(self) -> None:
        def rows(organization: Organization) -> list[tuple]:
            with tenant_atomic(organization.id):
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
                return list(
                    Integration.objects.filter(provider=IntegrationProvider.HTTP).values_list(
                        "id", "secret_headers"
                    )
                )

        self.assertEqual(rows(self.other), [])
        own = rows(self.organization)
        self.assertEqual([row[0] for row in own], [self.server.id])
        self.assertIn("shop-secret-token", own[0][1])
