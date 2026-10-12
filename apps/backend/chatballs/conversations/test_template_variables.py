from chatballs.conversations.models import ConnectionIdentity, ContactFieldValue
from chatballs.conversations.template_models import ReplyTemplate
from chatballs.conversations.template_variable_test_base import VariableTestBase
from chatballs.conversations.template_variables import CONTACT_FIELDS, LEGACY_VARIABLES, field_key


class TemplateVariableTests(VariableTestBase):
    def test_catalog_includes_legacy_standard_and_current_schema_without_values(self):
        items = self.catalog(self.dialog).json()["items"]
        keys = {item["key"] for item in items}
        self.assertEqual(keys, {
            *LEGACY_VARIABLES, *(f"contact.{field}" for field in CONTACT_FIELDS),
            *(field_key(self.connection.pk, key) for key in ("status", "enabled", "count")),
        })
        self.assertTrue(all("value" not in item for item in items))
        self.assertEqual(next(item for item in items if item["key"] == self.key)["type"], "enum")
        self.employee.user.ui_language = "en"
        self.employee.user.save(update_fields=["ui_language"])
        english = self.catalog().json()["items"]
        self.assertEqual(english[0]["label"], "Client name")

    def test_render_reads_current_contact_actor_and_organization_and_display_values(self):
        self.value("status", "ready")
        self.value("enabled", False)
        self.value("count", 0)
        text = " | ".join("{{" + key + "}}" for key in (
            *LEGACY_VARIABLES, *(f"contact.{field}" for field in CONTACT_FIELDS),
            self.key, field_key(self.connection.pk, "enabled"), field_key(self.connection.pk, "count"),
        ))
        template_id = self.template(text)
        result = self.render(template_id)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), {
            "text": "Visible | Operator | Library | current@client.test | +79991234567 | Client company | City | Description | Ready | Нет | 0",
            "unfilledKeys": [],
        })
        # The operator is the invoking employee, not the dialog's assignee.
        self.dialog.assigned_operator = self.colleague.user
        self.dialog.save(update_fields=["assigned_operator"])
        self.contact.name = "Updated client"
        self.contact.save(update_fields=["name"])
        self.organization.name = "Updated organization"
        self.organization.save(update_fields=["name"])
        self.employee.user.full_name = "Updated operator"
        self.employee.user.ui_language = "en"
        self.employee.user.save(update_fields=["full_name", "ui_language"])
        self.connection.config["fields"][0]["options"][0]["label"] = "New label"
        self.connection.save(update_fields=["config"])
        rendered = self.render(template_id).json()["text"]
        self.assertTrue(rendered.startswith("Updated client | Updated operator | Updated organization"))
        self.assertTrue(rendered.endswith("New label | No | 0"))

    def test_absent_null_blank_and_deleted_fields_remain_as_markers(self):
        keys = [self.key, field_key(self.connection.pk, "enabled"), field_key(self.connection.pk, "count")]
        text = " ".join("{{ " + key + " }}" for key in [*keys, self.key])
        template_id = self.template(text)
        self.value("enabled", None)
        self.assertEqual(self.render(template_id).json(), {"text": text, "unfilledKeys": keys})
        self.value("status", "ready")
        self.value("count", 0)
        self.connection.config["fields"] = []
        self.connection.save(update_fields=["config"])
        self.assertTrue(ContactFieldValue.objects.filter(contact=self.contact, key="status").exists())
        self.assertEqual(self.render(template_id).json(), {"text": text, "unfilledKeys": keys})
        self.assertNotIn(self.key, {item["key"] for item in self.catalog().json()["items"]})
        patched = self.client.patch(f"{self.base}{template_id}/", {"text": text}, format="json")
        self.assertEqual(patched.status_code, 400)
        self.assertIn(self.key, patched.json()["detail"])
        renamed = self.client.patch(f"{self.base}{template_id}/", {"title": "Renamed"}, format="json")
        self.assertEqual(renamed.status_code, 200)

    def test_guest_and_blank_standard_values_stay_unfilled(self):
        self.contact.name = "Guest · abc123"
        self.contact.email = "   "
        self.contact.save(update_fields=["name", "email"])
        ConnectionIdentity.objects.create(
            organization=self.organization, contact=self.contact, connection=self.connection,
            external_user_id="abc123456789", display_name=self.contact.name,
        )
        text = "Hello {{client_name}}, {{ contact.email }} / {{client_name}}"
        result = self.render(self.template(text)).json()
        self.assertEqual(result, {"text": text, "unfilledKeys": ["client_name", "contact.email"]})

    def test_unknown_keys_rejected_on_create_and_patch_including_dotted_and_malformed(self):
        template_id = self.template("Hello {{client_name}}")
        for key in ("unknown", "contact.missing", "contact.fields.999999.status", "unknown-key", "bad key", ""):
            with self.subTest(key=key):
                text = "{{" + key + "}}"
                created = self.create(text=text, title="Invalid")
                updated = self.client.patch(f"{self.base}{template_id}/", {"text": text}, format="json")
                for response in (created, updated):
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(text, response.json()["detail"])
        self.assertEqual(ReplyTemplate.objects.get(pk=template_id).text, "Hello {{client_name}}")

    def test_connection_namespace_and_removed_enum_option_do_not_resolve_stale_data(self):
        second_connection, second_dialog = self.web_dialog(self.organization, "Second")
        second_key = field_key(second_connection.pk, "status")
        self.value("status", "ready", second_dialog)
        self.value("status", "ready")
        text = "{{" + self.key + "}} / {{" + second_key + "}}"
        template_id = self.template(text)
        self.assertEqual(self.render(template_id).json(), {
            "text": "Ready / {{" + second_key + "}}", "unfilledKeys": [second_key],
        })
        self.assertEqual(self.render(template_id, second_dialog).json(), {
            "text": "{{" + self.key + "}} / Ready", "unfilledKeys": [self.key],
        })
        self.connection.config["fields"][0]["options"] = []
        self.connection.save(update_fields=["config"])
        self.assertEqual(self.render(template_id).json(), {"text": text, "unfilledKeys": [self.key, second_key]})
