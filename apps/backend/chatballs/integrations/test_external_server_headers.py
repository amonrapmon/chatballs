"""Заголовки внешнего сервера: секретные — в шифре и не в ответах API (SPEC-0023 R-1)."""

from __future__ import annotations

from django.db import connection

from chatballs.i18n import t
from chatballs.integrations.external_headers import request_headers
from chatballs.integrations.external_server_testing import (
    TOKEN,
    URL,
    ExternalServerTestCase,
    order_status,
)
from chatballs.integrations.models import Integration


class SecretHeaderTests(ExternalServerTestCase):
    def _created(self) -> dict:
        response = self._create("HTTP", order_status())
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["integration"]

    def test_secret_header_is_encrypted_and_never_returned(self) -> None:
        created = self._created()

        self.assertEqual(
            created["externalServer"]["headers"],
            [
                {"name": "Authorization", "secret": True, "value": ""},
                {"name": "X-Shop-Id", "secret": False, "value": "obed-main"},
            ],
        )
        listed = self.client.get(URL)
        for body in (self._create("HTTP", order_status(), name="Ещё").content, listed.content):
            self.assertNotIn("shop-secret-token", body.decode())
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT secret_headers, config::text FROM integrations_integration WHERE id = %s",
                [created["id"]],
            )
            column, config = cursor.fetchone()
        self.assertTrue(column)
        self.assertNotIn("shop-secret-token", column)
        self.assertNotIn("shop-secret-token", config)
        self.assertEqual(
            request_headers(Integration.objects.get(id=created["id"])),
            {"Authorization": TOKEN, "X-Shop-Id": "obed-main"},
        )

    def test_empty_secret_value_keeps_the_stored_one(self) -> None:
        created = self._created()
        detail = f"{URL}{created['id']}/"

        kept = self.client.patch(
            detail, {"externalServer": order_status(headers=created["externalServer"]["headers"])}, format="json"
        )
        self.assertEqual(kept.status_code, 200, kept.content)
        self.assertEqual(
            request_headers(Integration.objects.get(id=created["id"]))["Authorization"], TOKEN
        )

        replaced = self.client.patch(
            detail,
            {"externalServer": order_status(headers=[{"name": "Authorization", "secret": True, "value": "Bearer new"}])},
            format="json",
        )
        self.assertEqual(replaced.status_code, 200, replaced.content)
        self.assertEqual(
            request_headers(Integration.objects.get(id=created["id"])), {"Authorization": "Bearer new"}
        )

    def test_update_without_settings_leaves_them_untouched(self) -> None:
        created = self._created()

        response = self.client.patch(f"{URL}{created['id']}/", {"isActive": False}, format="json")

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()["integration"]
        self.assertFalse(payload["isActive"])
        self.assertEqual(payload["externalServer"], created["externalServer"])
        self.assertEqual(
            request_headers(Integration.objects.get(id=created["id"]))["Authorization"], TOKEN
        )

    def test_header_rules(self) -> None:
        cases = (
            ([{"name": "X-Key", "secret": True, "value": ""}], "integrations.tool_header_value_required", "X-Key"),
            ([{"name": "Bad Name", "value": "1"}], "integrations.tool_header_invalid", "Bad Name"),
            ([{"name": "Host", "value": "evil.test"}], "integrations.tool_header_invalid", "Host"),
            ([{"name": "X-Key", "value": "a\r\nX-Other: b"}], "integrations.tool_header_invalid", "X-Key"),
            (
                [{"name": "X-Key", "value": "1"}, {"name": "x-key", "value": "2"}],
                "integrations.tool_header_duplicate",
                "x-key",
            ),
        )
        for headers, key, name in cases:
            with self.subTest(headers=headers):
                errors = self._errors(self._create("HTTP", order_status(headers=headers)))
                self.assertEqual(errors, {"headers": [t(key, name=name)]})
