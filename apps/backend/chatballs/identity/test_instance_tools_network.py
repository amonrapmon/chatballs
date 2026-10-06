"""Настройка «адреса локальной сети для инструментов агентов» (SPEC-0023 R-17).

Она касается агентов всех организаций установки, поэтому и видит, и меняет её
только администратор установки; кто и когда включил — хранится и пишется в
журнал аудита.
"""

from __future__ import annotations

from django.test import TestCase

from chatballs.identity.audit_catalog import audit_action_label
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.instance_settings import InstanceSettings, tools_private_network_allowed
from chatballs.identity.models import (
    AuditEvent,
    EmployeeRole,
    HumanUser,
    Organization,
    OrganizationMembership,
)
from chatballs.integrations.tool_network import ToolAddressRejected, check_tool_url
from chatballs.testing import TenantAPIClient

PASSWORD = "Owner-Password-2026!"
URL = "/api/v1/instance/settings/tools-network/"
ACTIONS = (
    "administration.tools_private_network_enabled",
    "administration.tools_private_network_disabled",
)


class InstanceToolsNetworkTests(TestCase):
    def setUp(self) -> None:
        self.admin = bootstrap_owner(email="tools-admin@example.com", password=PASSWORD).owner
        other_org = Organization.objects.create(name="Other", slug="tools-other-org")
        self.other_owner = HumanUser.objects.create_user(
            email="tools-other-owner@example.com", password=PASSWORD, full_name="Other Owner"
        )
        OrganizationMembership.objects.create(
            organization=other_org, user=self.other_owner, role=EmployeeRole.OWNER, position_title="Owner"
        )

    def _client(self, user: HumanUser | None) -> TenantAPIClient:
        client = TenantAPIClient()
        if user is not None:
            client.force_authenticate(user)
        return client

    def _events(self) -> list[AuditEvent]:
        return list(AuditEvent.objects.filter(action__in=ACTIONS).order_by("id"))

    def test_setting_is_off_by_default(self) -> None:
        payload = self._client(self.admin).get(URL).json()["toolsNetwork"]

        self.assertEqual(payload, {"enabled": False, "enabledBy": None, "enabledAt": None})
        self.assertFalse(tools_private_network_allowed())

    def test_admin_enables_and_the_actor_and_time_are_kept(self) -> None:
        response = self._client(self.admin).patch(URL, {"enabled": True}, format="json")

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()["toolsNetwork"]
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["enabledBy"]["id"], self.admin.id)
        self.assertTrue(payload["enabledAt"])
        row = InstanceSettings.load()
        self.assertEqual(row.tools_private_network_enabled_by, self.admin)
        self.assertIsNotNone(row.tools_private_network_enabled_at)
        self.assertTrue(tools_private_network_allowed())
        self.assertEqual(self._client(self.admin).get(URL).json()["toolsNetwork"], payload)

    def test_change_is_written_to_the_audit_log(self) -> None:
        client = self._client(self.admin)
        client.patch(URL, {"enabled": True}, format="json")
        # Повтор того же значения — не изменение.
        client.patch(URL, {"enabled": True}, format="json")
        client.patch(URL, {"enabled": False}, format="json")

        events = self._events()
        self.assertEqual([event.action for event in events], list(ACTIONS))
        for event in events:
            self.assertEqual(event.actor, self.admin)
            self.assertIsNone(event.organization)
            self.assertEqual(event.object_type, "InstanceSettings")
            self.assertTrue(audit_action_label(event.action))

    def test_disabling_clears_the_actor_and_closes_private_ranges(self) -> None:
        client = self._client(self.admin)
        client.patch(URL, {"enabled": True}, format="json")

        payload = client.patch(URL, {"enabled": False}, format="json").json()["toolsNetwork"]

        self.assertEqual(payload, {"enabled": False, "enabledBy": None, "enabledAt": None})
        self.assertFalse(tools_private_network_allowed())

    def test_value_must_be_boolean(self) -> None:
        client = self._client(self.admin)
        for body in ({}, {"enabled": "yes"}, {"enabled": 1}, {"enabled": None}):
            with self.subTest(body=body):
                self.assertEqual(client.patch(URL, body, format="json").status_code, 400)
        self.assertFalse(tools_private_network_allowed())
        self.assertEqual(self._events(), [])

    def test_organization_owner_can_neither_read_nor_change(self) -> None:
        client = self._client(self.other_owner)

        self.assertEqual(client.get(URL).status_code, 403)
        self.assertEqual(client.patch(URL, {"enabled": True}, format="json").status_code, 403)
        # Общие настройки установки он читает, но признака в них нет.
        shared = client.get("/api/v1/instance/settings/")
        self.assertEqual(shared.status_code, 200)
        self.assertNotIn("tools", str(shared.json()).lower())
        self.assertFalse(tools_private_network_allowed())
        self.assertEqual(self._events(), [])

    def test_anonymous_is_refused(self) -> None:
        client = self._client(None)

        self.assertIn(client.get(URL).status_code, (401, 403))
        self.assertIn(client.patch(URL, {"enabled": True}, format="json").status_code, (401, 403))
        self.assertFalse(tools_private_network_allowed())

    def test_address_policy_follows_the_setting(self) -> None:
        with self.assertRaises(ToolAddressRejected):
            check_tool_url("http://192.168.1.20/")

        self._client(self.admin).patch(URL, {"enabled": True}, format="json")

        self.assertEqual(check_tool_url("http://192.168.1.20/").address, "192.168.1.20")
        with self.assertRaises(ToolAddressRejected):
            check_tool_url("http://127.0.0.1/")
        with self.assertRaises(ToolAddressRejected):
            check_tool_url("http://postgres:5432/")
