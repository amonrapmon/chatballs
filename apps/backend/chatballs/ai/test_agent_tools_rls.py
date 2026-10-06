"""Инструменты агента под реальной ролью backend-app: чужая организация их не видит.

Обычные тесты ходят в базу ролью-владельцем схемы, для которой RLS открыта.
Здесь запросы идут ролью ``chatballs_runtime_app``, как в production.
"""

from __future__ import annotations

from django.db import DatabaseError, connection
from django.test import TransactionTestCase
from django.utils import timezone

from chatballs.ai.agent_card import ensure_channel_agent
from chatballs.ai.models import AgentTool, AIAgent
from chatballs.channels.models import Channel
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import EmployeeRole, HumanUser, Organization, OrganizationMembership
from chatballs.integrations.models import (
    Integration,
    IntegrationKind,
    IntegrationProvider,
    ToolReadOnlyConfirmation,
)
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient

TOOLS = [
    {"name": "get_order_status", "title": "Статус заказа", "description": "", "read_only_hint": True},
    {"name": "cancel_order", "title": "", "description": "", "read_only_hint": False},
]


class AgentToolsRuntimeRoleTests(TransactionTestCase):
    def setUp(self) -> None:
        self.owner = bootstrap_owner(email="rls-tools@example.com", password="temporary-password").owner
        self.organization = Organization.objects.get(slug="demo")
        self.server = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.EXTERNAL_SERVER,
            provider=IntegrationProvider.MCP,
            name="Магазин",
            config={"url": "https://mcp.example.test/mcp", "headers": []},
            tools=TOOLS,
            tools_refreshed_at=timezone.now(),
        )
        self.agent = self._agent(self.organization, "rls-tools")
        self.other = Organization.objects.create(name="Other", slug="rls-tools-other")
        self.other_owner = HumanUser.objects.create_user(email="rls-tools-other@example.com")
        OrganizationMembership.objects.create(
            organization=self.other, user=self.other_owner, role=EmployeeRole.OWNER, position_title="Owner"
        )
        self.other_agent = self._agent(self.other, "rls-tools-other")

    def _agent(self, organization: Organization, code: str) -> AIAgent:
        channel = Channel.objects.create(organization=organization, code=code, name=code)
        return ensure_channel_agent(channel)

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

    def _card(self, organization: Organization, agent: AIAgent) -> str:
        return f"/api/v1/organizations/{organization.public_id}/agents/{agent.channel_id}/"

    def _confirm_url(self, organization: Organization) -> str:
        return (
            f"/api/v1/organizations/{organization.public_id}/integrations/"
            f"{self.server.id}/tools/read-only/confirm/"
        )

    def _body(self, *names: str) -> dict:
        return {"tools": [{"integrationId": self.server.id, "name": name} for name in names]}

    def _enable_own_tools(self) -> None:
        """Подтверждение и два включённых инструмента — от имени своей организации."""
        client = self._client(self.owner)
        confirmed = self._as_app_role(
            lambda: client.post(
                self._confirm_url(self.organization),
                {"name": "cancel_order", "confirmed": True},
                format="json",
            )
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        saved = self._as_app_role(
            lambda: client.patch(
                self._card(self.organization, self.agent),
                self._body("get_order_status", "cancel_order"),
                format="json",
            )
        )
        self.assertEqual(saved.status_code, 200, saved.content)

    def test_own_organization_manages_tools_under_app_role(self) -> None:
        self._enable_own_tools()

        client = self._client(self.owner)
        card = self._as_app_role(lambda: client.get(self._card(self.organization, self.agent)))

        self.assertEqual(card.status_code, 200, card.content)
        (server,) = card.json()["agent"]["tools"]
        self.assertEqual(
            [(tool["name"], tool["readOnly"], tool["enabled"]) for tool in server["tools"]],
            [("get_order_status", True, True), ("cancel_order", True, True)],
        )
        self.assertEqual(
            set(AgentTool.objects.values_list("organization_id", "tool_name")),
            {(self.organization.id, "get_order_status"), (self.organization.id, "cancel_order")},
        )
        confirmation = ToolReadOnlyConfirmation.objects.get()
        self.assertEqual(
            (confirmation.organization_id, confirmation.confirmed_by), (self.organization.id, self.owner)
        )

    def test_foreign_organization_cannot_reach_tools_under_app_role(self) -> None:
        self._enable_own_tools()
        client = self._client(self.other_owner)

        own_card = self._as_app_role(lambda: client.get(self._card(self.other, self.other_agent)))
        enabled = self._as_app_role(
            lambda: client.patch(
                self._card(self.other, self.other_agent), self._body("get_order_status"), format="json"
            )
        )
        foreign_card = self._as_app_role(
            lambda: client.patch(self._card(self.other, self.agent), {"tools": []}, format="json")
        )
        confirmed = self._as_app_role(
            lambda: client.post(
                self._confirm_url(self.other), {"name": "cancel_order", "confirmed": True}, format="json"
            )
        )

        self.assertEqual(own_card.status_code, 200, own_card.content)
        # Чужой сервер не попадает в список доступных и не включается.
        self.assertEqual(own_card.json()["agent"]["tools"], [])
        self.assertEqual(enabled.status_code, 400, enabled.content)
        self.assertEqual(foreign_card.status_code, 404)
        self.assertEqual(confirmed.status_code, 404)
        self.assertEqual(AgentTool.objects.filter(agent=self.agent).count(), 2)
        self.assertFalse(AgentTool.objects.filter(agent=self.other_agent).exists())

    def _rows(self, organization: Organization) -> tuple[list[str], list[str]]:
        with tenant_atomic(organization.id):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            return (
                sorted(AgentTool.objects.values_list("tool_name", flat=True)),
                list(ToolReadOnlyConfirmation.objects.values_list("tool_name", flat=True)),
            )

    def test_foreign_tenant_reads_no_rows(self) -> None:
        self._enable_own_tools()

        self.assertEqual(self._rows(self.other), ([], []))
        self.assertEqual(
            self._rows(self.organization), (["cancel_order", "get_order_status"], ["cancel_order"])
        )

    def _insert(self, tenant: Organization, row: AgentTool | ToolReadOnlyConfirmation) -> None:
        """Вставка в обход проверок модели — как сделал бы ошибочный код."""
        with tenant_atomic(tenant.id):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            type(row).objects.bulk_create([row])

    def test_foreign_tenant_cannot_write_rows(self) -> None:
        forged = [
            # Строка чужой организации из своего контекста.
            AgentTool(organization=self.organization, agent=self.agent, integration=self.server, tool_name="x"),
            # Своя строка, указывающая на чужого агента и чужой сервер.
            AgentTool(organization=self.other, agent=self.agent, integration=self.server, tool_name="x"),
            # Свой агент с чужим сервером.
            AgentTool(organization=self.other, agent=self.other_agent, integration=self.server, tool_name="x"),
            ToolReadOnlyConfirmation(
                organization=self.organization,
                integration=self.server,
                tool_name="cancel_order",
                confirmed_at=timezone.now(),
            ),
            ToolReadOnlyConfirmation(
                organization=self.other,
                integration=self.server,
                tool_name="cancel_order",
                confirmed_at=timezone.now(),
            ),
        ]

        for row in forged:
            with self.subTest(row=str(row)), self.assertRaises(DatabaseError):
                self._insert(self.other, row)
        self.assertFalse(AgentTool.objects.exists())
        self.assertFalse(ToolReadOnlyConfirmation.objects.exists())
