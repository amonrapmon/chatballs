"""Direct send acceptance on real services and the isolated Django test database."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection

from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    ExpectedResponder,
    Message,
    MessageAuthor,
)
from chatballs.conversations.services import post_operator_message
from chatballs.conversations.template_send_guard import UnfilledTemplateVariables
from chatballs.conversations.template_variable_test_base import VariableTestBase
from chatballs.conversations.template_variables import CONTACT_FIELDS, LEGACY_VARIABLES
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import AuditEvent
from chatballs.tenancy.database import tenant_atomic


class TemplateSendingTests(VariableTestBase):
    def send(self, text, dialog=None, **extra):
        dialog = dialog or self.dialog
        return self.client.post(
            f"/api/v1/organizations/{self.organization.public_id}/conversations/{dialog.pk}/messages/",
            {"text": text, **extra}, format="json",
        )

    def assert_untouched(self):
        self.dialog.refresh_from_db()
        self.assertEqual(self.dialog.control_mode, ControlMode.AI)
        self.assertIsNone(self.dialog.assigned_operator_id)
        self.assertEqual(self.dialog.expected_responder, ExpectedResponder.AI)
        self.assertEqual(self.dialog.last_activity_at, self.initial_activity)
        self.assertFalse(self.dialog.messages.exists())
        self.assertFalse(self.dialog.domain_events.exists())
        self.assertFalse(AuditEvent.objects.filter(organization=self.organization).exists())

    def setUp(self):
        super().setUp()
        self.initial_activity = self.dialog.last_activity_at

    def test_direct_api_blocks_all_known_markers_once_in_text_order_before_claim(self):
        keys = [self.key, *LEGACY_VARIABLES, *(f"contact.{field}" for field in CONTACT_FIELDS)]
        text = " / ".join("{{ " + key + " }}" for key in [*keys, self.key])
        response = self.send(text, unfilledKeys=[], templateId=None)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["unfilledKeys"], keys)
        self.assertTrue(response.json()["detail"])
        self.assert_untouched()

    def test_service_blocks_markers_without_http_or_template_metadata(self):
        with self.assertRaises(UnfilledTemplateVariables) as error:
            post_operator_message(context=self.context, conversation=self.dialog, text="{{contact.email}}")
        self.assertEqual(error.exception.keys, ["contact.email"])
        self.assert_untouched()

    def test_suggestion_send_cannot_bypass_guard(self):
        response = self.send(
            "{{client_name}}", suggestionId="00000000-0000-4000-8000-000000000001",
            operationKey="unfilled-suggestion",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["unfilledKeys"], ["client_name"])
        self.assert_untouched()

    def test_deleted_field_remains_blocked_after_render_and_accepts_manual_edit(self):
        template_id = self.template("Status: {{" + self.key + "}}")
        self.connection.config["fields"] = []
        self.connection.save(update_fields=["config"])
        result = self.render(template_id).json()
        self.assertEqual(result["unfilledKeys"], [self.key])
        blocked = self.send(result["text"])
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(blocked.json()["unfilledKeys"], [self.key])
        self.assertFalse(self.dialog.messages.exists())
        self.assert_sent(self.send(result["text"].replace("{{" + self.key + "}}", "Manually filled")),
                         "Status: Manually filled")

    def assert_sent(self, response, text):
        self.assertEqual(response.status_code, 201, response.data)
        message = Message.objects.get(pk=response.json()["message"]["id"])
        self.assertEqual(message.text, text)
        self.assertEqual(message.author_type, MessageAuthor.OPERATOR)
        self.assertEqual(self.dialog.domain_events.filter(event_type="ACCEPTED").count(), 1)
        self.assertEqual(self.dialog.domain_events.filter(event_type="PUBLIC_REPLY", actor_kind="HUMAN").count(),
                         self.dialog.messages.filter(author_type=MessageAuthor.OPERATOR).count())
        self.assertEqual(message.author_user, self.employee.user)
        self.dialog.refresh_from_db()
        self.assertEqual(self.dialog.control_mode, ControlMode.HUMAN)
        self.assertEqual(self.dialog.assigned_operator, self.employee.user)
        self.assertEqual(self.dialog.expected_responder, ExpectedResponder.CUSTOMER)
        history = self.client.get(
            f"/api/v1/organizations/{self.organization.public_id}/conversations/{self.dialog.pk}/messages/",
        )
        self.assertIn(text, [item["text"] for item in history.json()["items"]])

    def test_legacy_shared_template_renders_and_edited_text_uses_normal_send(self):
        response = self.create(
            text="Hello {{client_name}}, {{operator_name}} / {{company}}",
            client=self.owner_client, scope="SHARED",
        )
        self.assertEqual(response.status_code, 201)
        template_id = response.json()["template"]["id"]
        result = self.render(template_id).json()
        self.assertEqual(result, {"text": "Hello Visible, Operator / Library", "unfilledKeys": []})
        text = result["text"] + ". Edited before sending."
        self.assert_sent(self.send(text), text)

    def test_plain_text_unknown_markers_and_single_braces_keep_compatibility(self):
        for text in ("Ordinary reply", "{date} / {{unknown}} / {{contact.missing}}"):
            with self.subTest(text=text):
                self.assert_sent(self.send(text), text)

    def test_attachment_caption_cannot_bypass_guard_before_claim_or_storage(self):
        response = self.client.post(
            f"/api/v1/organizations/{self.organization.public_id}/conversations/{self.dialog.pk}/attachments/",
            {"file": SimpleUploadedFile("note.txt", b"content", content_type="text/plain"),
             "text": "Caption {{client_name}}"}, format="multipart",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.json()["unfilledKeys"], ["client_name"])
        self.assert_untouched()

    def test_hidden_and_foreign_dialogs_keep_access_errors(self):
        group = EmployeeGroup.objects.create(organization=self.organization, name="Hidden")
        _, hidden = self.web_dialog(self.organization, "Hidden", group=group)
        _, foreign = self.web_dialog(self.foreign, "Foreign")
        for dialog in (hidden, foreign):
            response = self.send("{{client_name}}", dialog=dialog)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn("unfilledKeys", response.json())
        with self.assertRaises(Conversation.DoesNotExist):
            post_operator_message(context=self.context, conversation=foreign, text="{{client_name}}")

    def test_guard_and_edited_send_work_under_runtime_app_role_with_english_error(self):
        self.employee.user.ui_language = "en"
        self.employee.user.save(update_fields=["ui_language"])
        with tenant_atomic(self.context):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            response = self.send("{{company}}")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json(), {
                "detail": "Fill in the variables or remove their markers before sending",
                "unfilledKeys": ["company"],
            })
            self.assert_sent(self.send("Company filled manually"), "Company filled manually")
