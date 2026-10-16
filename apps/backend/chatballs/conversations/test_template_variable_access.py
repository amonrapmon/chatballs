from django.db import connection
from django.utils import timezone

from chatballs.conversations.template_models import ReplyTemplate
from chatballs.conversations.template_variable_test_base import VariableTestBase
from chatballs.conversations.template_variables import field_key
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import EmployeeRole
from chatballs.identity.supervision_models import EmployeeGroupSupervision
from chatballs.tenancy.database import tenant_atomic


class TemplateVariableAccessTests(VariableTestBase):
    def setUp(self):
        super().setUp()
        group = EmployeeGroup.objects.create(organization=self.organization, name="Hidden")
        self.hidden_connection, self.hidden_dialog = self.web_dialog(self.organization, "Hidden", group)
        self.foreign_connection, self.foreign_dialog = self.web_dialog(self.foreign, "Foreign")
        self.hidden_key = field_key(self.hidden_connection.pk, "status")
        self.foreign_key = field_key(self.foreign_connection.pk, "status")
        self.value("status", "ready")
        self.value("status", "ready", self.hidden_dialog)
        self.value("status", "ready", self.foreign_dialog)
        self.template_id = self.template("{{" + self.key + "}}")

    def test_catalog_and_saving_use_current_visibility_not_submitted_ids(self):
        keys = {item["key"] for item in self.catalog().json()["items"]}
        self.assertIn(self.key, keys)
        self.assertNotIn(self.hidden_key, keys)
        self.assertNotIn(self.foreign_key, keys)
        for dialog in (self.hidden_dialog, self.foreign_dialog):
            with self.subTest(dialog=dialog.pk):
                self.assertEqual(self.catalog(dialog).status_code, 404)
                self.assertEqual(self.render(self.template_id, dialog).status_code, 404)
        for key in (self.hidden_key, self.foreign_key):
            response = self.create(
                title="Denied", text="{{" + key + "}}", connectionId=self.hidden_connection.pk,
                conversationId=self.hidden_dialog.pk, fields=[{"key": key}],
            )
            self.assertEqual(response.status_code, 400)
            self.assertIn(key, response.json()["detail"])
        # Assignment changes genuine server-side visibility.
        self.hidden_dialog.assigned_operator = self.employee.user
        self.hidden_dialog.save(update_fields=["assigned_operator"])
        self.assertIn(self.hidden_key, {item["key"] for item in self.catalog().json()["items"]})
        template_id = self.template("{{" + self.hidden_key + "}}", title="Assigned")
        self.assertEqual(self.render(template_id, self.hidden_dialog).json()["text"], "Ready")
        self.hidden_dialog.assigned_operator = None
        self.hidden_dialog.save(update_fields=["assigned_operator"])
        self.assertEqual(self.render(template_id, self.hidden_dialog).status_code, 404)

    def test_template_access_is_membership_scoped_even_for_owner(self):
        personal = ReplyTemplate.objects.create(
            organization=self.organization, owner=self.colleague, title="Private", text="{{client_name}}",
        )
        foreign = ReplyTemplate.objects.create(
            organization=self.foreign, owner=self.foreign_member, title="Foreign", text="{{client_name}}",
        )
        for client in (self.client, self.owner_client):
            for template in (personal, foreign):
                with self.subTest(template=template.pk, client=client):
                    self.assertEqual(self.render(template.pk, client=client).status_code, 404)
        shared = ReplyTemplate.objects.create(
            organization=self.organization, title="Shared", text="{{client_name}}",
        )
        self.assertEqual(self.render(shared.pk).json()["text"], "Visible")
        foreign_client = self.client_for(self.foreign_member)
        response = foreign_client.post(
            f"/api/v1/organizations/{self.foreign.public_id}/conversations/templates/{self.template_id}/render/",
            {"conversationId": self.foreign_dialog.pk}, format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_client_values_text_contact_and_tenant_cannot_override_server_data(self):
        for extra in (
            {"values": {self.key: "Forged"}}, {"text": "Forged"},
            {"contactId": self.foreign_dialog.contact_id}, {"operatorId": self.owner.pk},
            {"organizationId": self.foreign.pk}, {"connectionId": self.foreign_connection.pk},
        ):
            with self.subTest(extra=extra):
                self.assertEqual(self.render(self.template_id, **extra).status_code, 400)
        catalog = self.catalog(connectionId=self.hidden_connection.pk, organizationId=self.foreign.pk)
        self.assertNotIn(self.hidden_key, {item["key"] for item in catalog.json()["items"]})
        self.assertNotIn(self.foreign_key, {item["key"] for item in catalog.json()["items"]})
        self.assertEqual(self.render(self.template_id).json(), {"text": "Ready", "unfilledKeys": []})

    def test_invalid_dialog_ids_and_blocked_membership_do_not_resolve(self):
        url = f"{self.base}{self.template_id}/render/"
        for value in (None, True, 0, -1, [], "bad", "9" * 30, "9" * 19, 2**63):
            with self.subTest(value=value):
                response = self.client.post(url, {"conversationId": value}, format="json")
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"conversationId": 9999999}, format="json").status_code, 404)
        self.employee.blocked_at = timezone.now()
        self.employee.save(update_fields=["blocked_at"])
        # Tenant middleware hides organizations without an active membership.
        self.assertEqual(self.catalog().status_code, 404)
        self.assertEqual(self.render(self.template_id).status_code, 404)

    def test_catalog_and_substitution_work_under_real_runtime_app_role(self):
        with tenant_atomic(self.context):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            items = self.catalog().json()["items"]
            self.assertIn(self.key, {item["key"] for item in items})
            self.assertNotIn(self.foreign_key, {item["key"] for item in items})
            self.assertEqual(self.render(self.template_id).json(), {"text": "Ready", "unfilledKeys": []})
            self.assertEqual(self.render(self.template_id, self.foreign_dialog).status_code, 404)

    def test_catalog_and_substitution_follow_main_supervision_access_and_revocation(self):
        self.employee.role = EmployeeRole.SUPERVISOR
        self.employee.save(update_fields=["role"])
        link = EmployeeGroupSupervision.objects.create(
            organization=self.organization, employee=self.employee, group=self.hidden_dialog.group,
        )
        keys = {item["key"] for item in self.catalog().json()["items"]}
        self.assertIn(self.hidden_key, keys)
        self.assertNotIn(self.foreign_key, keys)
        template_id = self.template("{{" + self.hidden_key + "}}", title="Supervised")
        self.assertEqual(self.render(template_id, self.hidden_dialog).json(), {
            "text": "Ready", "unfilledKeys": [],
        })
        link.delete()
        self.assertNotIn(self.hidden_key, {item["key"] for item in self.catalog().json()["items"]})
        self.assertEqual(self.render(template_id, self.hidden_dialog).status_code, 404)
