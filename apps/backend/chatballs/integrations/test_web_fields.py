"""Свои поля веб-подключения: схема в config.fields и её публичная часть.

PATCH подключения проверяет схему целиком, а виджету на сайте уходит та же
схема без режима доступа AI (SPEC-0019 R-1, R-2; SPEC-0022 R-10, R-11, R-13).
"""

from django.test import TestCase
from rest_framework.test import APIClient as PublicClient

from chatballs.channels.models import Channel
from chatballs.i18n import t
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.testing import TenantAPIClient, system_tenant_context

ORDER_STATUS = {
    "key": "order_status",
    "label": "Статус заказа",
    "type": "enum",
    "options": [
        {"value": "cooking", "label": "Готовится", "color": "#faad14"},
        {"value": "on_the_way", "label": "В пути", "color": "#1677ff"},
    ],
    "aiAccess": "open",
    "order": 1,
}
CLIENT_ID = {"key": "user_id", "label": "ID клиента", "type": "string", "aiAccess": "hidden", "order": 0}


class WebFieldsSchemaTests(TestCase):
    def setUp(self) -> None:
        bootstrap_owner(email="fields-owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.channel = Channel.objects.create(
            organization=self.organization, code="obed", name="Столовая «Обед»"
        )
        self.integration = create_integration(
            context=system_tenant_context(self.organization),
            data=IntegrationInput(
                provider=IntegrationProvider.WEB,
                name="Сайт",
                channel_id=self.channel.id,
                config={"allowedOrigins": ["obed.example"]},
            ),
        )
        self.client = TenantAPIClient()
        self.client.login(username="fields-owner@example.com", password="temporary-password")

    def _patch(self, fields: object, **config: object):
        return self.client.patch(
            f"/api/v1/integrations/{self.integration.id}/",
            {"config": {"allowedOrigins": ["obed.example"], "fields": fields, **config}},
            format="json",
        )

    def _saved(self, fields: list) -> list:
        response = self._patch(fields)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["integration"]["config"]["fields"]

    def _rejected(self, fields: object, message: str) -> None:
        response = self._patch(fields)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], message)

    def test_schema_is_saved_in_order_with_server_ids(self) -> None:
        saved = self._saved([ORDER_STATUS, CLIENT_ID])

        self.assertEqual([field["key"] for field in saved], ["user_id", "order_status"])
        self.assertEqual([field["order"] for field in saved], [0, 1])
        self.assertTrue(all(field["id"] for field in saved))
        self.assertEqual(saved[1]["options"], ORDER_STATUS["options"])
        self.assertEqual([field["aiAccess"] for field in saved], ["hidden", "open"])
        self.integration.refresh_from_db()
        self.assertEqual(
            [field["ai_access"] for field in self.integration.config["fields"]], ["hidden", "open"]
        )
        self.assertFalse(any("ai_visible" in field for field in self.integration.config["fields"]))

    def test_access_mode_is_checked(self) -> None:
        for mode in ("hidden", "masked", "open"):
            with self.subTest(mode=mode):
                self.assertEqual(self._saved([{**CLIENT_ID, "aiAccess": mode}])[0]["aiAccess"], mode)
        self.assertEqual(self._saved([{"key": "note", "label": "Заметка", "type": "string"}])[0]["aiAccess"], "hidden")
        for mode in ("visible", "", True, 1):
            with self.subTest(mode=mode):
                self._rejected(
                    [{**CLIENT_ID, "aiAccess": mode}],
                    t("settings.web_field_ai_access_invalid", key="user_id"),
                )

    def test_email_and_phone_are_never_open(self) -> None:
        for field_type in ("email", "phone"):
            field = {"key": "contact", "label": "Связь", "type": field_type}
            with self.subTest(type=field_type):
                self._rejected(
                    [{**field, "aiAccess": "open"}],
                    t("settings.web_field_ai_access_mask_only", key="contact"),
                )
                for mode in ("hidden", "masked"):
                    self.assertEqual(self._saved([{**field, "aiAccess": mode}])[0]["aiAccess"], mode)

    def test_legacy_flag_is_translated_by_field_type(self) -> None:
        expected = {
            "string": "masked", "email": "masked", "phone": "masked", "url": "masked",
            "number": "open", "boolean": "open", "datetime": "open", "enum": "open",
        }
        for field_type, mode in expected.items():
            field = {"key": "legacy", "label": "Поле", "type": field_type}
            with self.subTest(type=field_type):
                self.assertEqual(self._saved([{**field, "aiVisible": True}])[0]["aiAccess"], mode)
                self.assertEqual(self._saved([{**field, "aiVisible": False}])[0]["aiAccess"], "hidden")

    def test_legacy_form_round_trip_keeps_and_toggles_the_mode(self) -> None:
        # Прежняя форма возвращает поле как получила и меняет только aiVisible.
        saved = self._saved([{"key": "amount", "label": "Сумма", "type": "number", "aiAccess": "masked"}])
        self.assertTrue(saved[0]["aiVisible"])

        untouched = self._saved([{**saved[0], "label": "Сумма заказа"}])
        self.assertEqual(untouched[0]["aiAccess"], "masked")

        off = self._saved([{**untouched[0], "aiVisible": False}])
        self.assertEqual((off[0]["aiAccess"], off[0]["aiVisible"]), ("hidden", False))

        on = self._saved([{**off[0], "aiVisible": True}])
        self.assertEqual(on[0]["aiAccess"], "open")

    def test_form_without_fields_keeps_the_schema(self) -> None:
        self._saved([CLIENT_ID])

        response = self.client.patch(
            f"/api/v1/integrations/{self.integration.id}/",
            {"config": {"allowedOrigins": ["obed.example"], "title": "Обед"}},
            format="json",
        )

        self.assertEqual([field["key"] for field in response.json()["integration"]["config"]["fields"]], ["user_id"])

    def test_key_of_a_saved_field_cannot_change(self) -> None:
        saved = self._saved([CLIENT_ID])

        self._rejected(
            [{**saved[0], "key": "client_id"}],
            t("settings.web_field_key_immutable", key="user_id"),
        )
        # Удалить поле и завести новое с другим ключом можно.
        self.assertEqual(self._saved([{**CLIENT_ID, "key": "client_id"}])[0]["key"], "client_id")

    def test_renaming_a_saved_field_keeps_its_id(self) -> None:
        saved = self._saved([CLIENT_ID])

        renamed = self._saved([{**saved[0], "label": "Номер клиента"}])

        self.assertEqual(renamed[0]["id"], saved[0]["id"])
        self.assertEqual(renamed[0]["label"], "Номер клиента")

    def test_invalid_keys_are_rejected(self) -> None:
        for key in ("Order", "1st", "_x", "order-status", "a" * 41, ""):
            with self.subTest(key=key):
                self._rejected([{**CLIENT_ID, "key": key}], t("settings.web_field_key_invalid", key=key))

    def test_reserved_keys_are_rejected(self) -> None:
        for key in ("name", "email", "phone"):
            with self.subTest(key=key):
                self._rejected([{**CLIENT_ID, "key": key}], t("settings.web_field_key_reserved", key=key))

    def test_duplicate_key_is_rejected(self) -> None:
        self._rejected([CLIENT_ID, {**CLIENT_ID, "label": "Ещё"}], t("settings.web_field_key_duplicate", key="user_id"))

    def test_more_than_thirty_fields_are_rejected(self) -> None:
        fields = [{**CLIENT_ID, "key": f"field_{index}"} for index in range(31)]

        self._rejected(fields, t("settings.web_fields_limit", limit=30))
        self.assertEqual(len(self._saved(fields[:30])), 30)

    def test_label_is_required_and_limited(self) -> None:
        self._rejected([{**CLIENT_ID, "label": " "}], t("settings.web_field_label_required", key="user_id"))
        self._rejected([{**CLIENT_ID, "label": "я" * 61}], t("settings.web_field_label_too_long", key="user_id", limit=60))
        self.assertEqual(self._saved([{**CLIENT_ID, "label": "я" * 60}])[0]["label"], "я" * 60)

    def test_unknown_type_is_rejected(self) -> None:
        self._rejected([{**CLIENT_ID, "type": "json"}], t("settings.web_field_type_invalid", key="user_id"))

    def test_options_belong_only_to_enum(self) -> None:
        self._rejected(
            [{**CLIENT_ID, "options": ORDER_STATUS["options"]}],
            t("settings.web_field_options_only_enum", key="user_id"),
        )

    def test_enum_options_are_checked(self) -> None:
        self._rejected(
            [{**ORDER_STATUS, "options": [{"value": "", "label": "Пусто"}]}],
            t("settings.web_field_option_invalid", key="order_status"),
        )
        self._rejected(
            [{**ORDER_STATUS, "options": [{"value": "cooking", "label": "Готовится", "color": "red"}]}],
            t("settings.web_field_option_invalid", key="order_status"),
        )
        self._rejected(
            [{**ORDER_STATUS, "options": [{"value": "cooking"}, {"value": "cooking"}]}],
            t("settings.web_field_option_duplicate", key="order_status", value="cooking"),
        )

    def test_fields_must_be_a_list(self) -> None:
        self._rejected({"user_id": "string"}, t("settings.web_fields_list"))

    def test_public_config_carries_the_schema_without_access_mode(self) -> None:
        self._saved([ORDER_STATUS, CLIENT_ID])
        widget_key = self.integration.web_chat_widget.public_key

        response = PublicClient().get("/api/v1/webchat/config/", {"widgetKey": widget_key}, HTTP_ORIGIN="https://obed.example")

        self.assertTrue(response.json()["available"])
        self.assertEqual(
            response.json()["fields"],
            [
                {"key": "user_id", "label": "ID клиента", "type": "string", "order": 0},
                {
                    "key": "order_status",
                    "label": "Статус заказа",
                    "type": "enum",
                    "options": ORDER_STATUS["options"],
                    "order": 1,
                },
            ],
        )
