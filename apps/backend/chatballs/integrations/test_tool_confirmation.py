"""Подтверждение «только читает» для MCP-инструмента (SPEC-0023 R-6)."""

from __future__ import annotations

from django.utils.dateparse import parse_datetime

from chatballs.ai.agent_tools_testing import AgentToolsTestCase
from chatballs.i18n import t
from chatballs.identity.audit_catalog import audit_action_label
from chatballs.identity.models import AuditEvent, HumanUser
from chatballs.integrations.models import ToolReadOnlyConfirmation

CONFIRMED = "integrations.tool_read_only_confirmed"
REVOKED = "integrations.tool_read_only_revoked"


class ToolConfirmationTests(AgentToolsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = HumanUser.objects.get(email="external-owner@example.com")
        self.owner.full_name = "Елена Кузнецова"
        self.owner.save(update_fields=["full_name"])

    def _tool(self, payload: dict, name: str = "cancel_order") -> dict:
        tools = payload["integration"]["externalServer"]["tools"]
        return next(tool for tool in tools if tool["name"] == name)

    def _events(self) -> list[AuditEvent]:
        return list(AuditEvent.objects.filter(action__in=(CONFIRMED, REVOKED)).order_by("id"))

    def _rejected(self, response, field: str, key: str) -> None:
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["errors"], {field: [t(key)]})
        self.assertFalse(ToolReadOnlyConfirmation.objects.exists())
        self.assertEqual(self._events(), [])

    def test_tool_has_no_confirmation_at_first(self) -> None:
        self.assertIsNone(self.mcp["externalServer"]["tools"][1]["readOnlyConfirmation"])

    def test_confirmation_keeps_the_author_and_the_time(self) -> None:
        response = self._confirm()

        self.assertEqual(response.status_code, 200, response.content)
        confirmation = self._tool(response.json())["readOnlyConfirmation"]
        row = ToolReadOnlyConfirmation.objects.get()
        self.assertEqual(
            confirmation,
            {
                "confirmedBy": {"id": self.owner.id, "name": "Елена Кузнецова"},
                "confirmedAt": row.confirmed_at.isoformat(),
            },
        )
        self.assertEqual(
            (row.organization_id, row.integration_id, row.tool_name, row.confirmed_by, row.revoked_at),
            (self.organization.id, self.mcp["id"], "cancel_order", self.owner, None),
        )
        self.assertIsNotNone(parse_datetime(confirmation["confirmedAt"]))
        # Отметка сервера при этом не меняется: подтвердил человек, а не сервер.
        self.assertFalse(self._tool(response.json())["readOnlyHint"])
        self.assertIsNone(self._tool(response.json(), "get_order_status")["readOnlyConfirmation"])

    def test_confirmation_is_written_to_the_audit_log(self) -> None:
        self._confirm()

        (event,) = self._events()
        self.assertEqual(
            (event.action, event.actor, event.organization, event.object_type, event.object_id),
            (CONFIRMED, self.owner, self.organization, "Integration", str(self.mcp["id"])),
        )
        self.assertEqual(event.payload, {"tool": "cancel_order"})
        self.assertTrue(audit_action_label(CONFIRMED))

    def test_revoking_keeps_the_author_and_the_time_and_is_audited(self) -> None:
        self._confirm()

        response = self._revoke()

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(self._tool(response.json())["readOnlyConfirmation"])
        row = ToolReadOnlyConfirmation.objects.get()
        self.assertEqual((row.confirmed_by, row.revoked_by), (self.owner, self.owner))
        self.assertGreaterEqual(row.revoked_at, row.confirmed_at)
        self.assertEqual([event.action for event in self._events()], [CONFIRMED, REVOKED])
        revoked = self._events()[1]
        self.assertEqual((revoked.actor, revoked.payload), (self.owner, {"tool": "cancel_order"}))
        self.assertTrue(audit_action_label(REVOKED))

    def test_tool_can_be_confirmed_again_after_revoking(self) -> None:
        self._confirm()
        self._revoke()

        response = self._confirm()

        self.assertEqual(response.status_code, 200, response.content)
        row = ToolReadOnlyConfirmation.objects.get()
        self.assertEqual((row.revoked_by, row.revoked_at), (None, None))
        self.assertIsNotNone(self._tool(response.json())["readOnlyConfirmation"])

    def test_confirmation_survives_a_list_refresh(self) -> None:
        self._confirm()

        refreshed = self._refresh(self.mcp)

        self.assertIsNotNone(self._tool({"integration": refreshed})["readOnlyConfirmation"])

    def test_confirmation_needs_the_checkbox(self) -> None:
        for confirmed in (False, None, "true", 1):
            self._rejected(
                self._confirm(confirmed=confirmed),
                "confirmed",
                "integrations.tool_confirmation_required",
            )

    def test_only_a_listed_tool_without_the_server_mark_is_confirmed(self) -> None:
        self._rejected(self._confirm("drop_database"), "name", "integrations.tool_not_in_list")
        self._rejected(
            self._confirm("get_order_status"), "name", "integrations.tool_read_only_by_server"
        )
        response = self.client.post(
            f"/api/v1/integrations/{self.http['id']}/tools/read-only/confirm/",
            {"name": "get_order_status", "confirmed": True},
            format="json",
        )
        self._rejected(response, "name", "integrations.tool_not_in_list")

    def test_revoking_a_tool_without_confirmation_is_rejected(self) -> None:
        self._rejected(self._revoke(), "name", "integrations.tool_not_confirmed")

    def test_unknown_server_is_not_found(self) -> None:
        response = self.client.post(
            "/api/v1/integrations/999999/tools/read-only/confirm/",
            {"name": "cancel_order", "confirmed": True},
            format="json",
        )

        self.assertEqual(response.status_code, 404)
