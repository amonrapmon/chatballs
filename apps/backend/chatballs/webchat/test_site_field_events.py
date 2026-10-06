from unittest.mock import patch

from django.db import transaction
from django.test import TestCase
from django.utils.translation import override

from chatballs.conversations.models import (
    ContactFieldValue,
    Conversation,
    LifecycleState,
    Message,
    MessageAuthor,
    SystemEvent,
)
from chatballs.conversations.serializers import _pending_count, message_payload, pending_counts_for
from chatballs.identity.models import EmployeeRole, HumanUser, OrganizationMembership
from chatballs.testing import TenantAPIClient
from chatballs.webchat import test_site_fields as storage_tests
from chatballs.webchat.services import messages_payload
from chatballs.webchat.site_fields import save_site_fields

FIELDS = [
    {"key": "status", "label": "Статус заказа", "type": "enum", "order": 2, "ai_access": "hidden",
     "options": [{"value": "cooking", "label": "Готовится", "color": "orange"},
                 {"value": "sent", "label": "В пути", "color": "blue"}]},
    {"key": "active", "label": "Активный заказ", "type": "boolean", "order": 1},
    {"key": "number", "label": "Номер", "type": "string", "order": 3},
]


class SiteFieldEventTests(TestCase):
    def setUp(self):
        storage_tests.SiteFieldApiTests.setUp(self)
        self.widget.integration.config = {"fields": FIELDS}
        self.widget.integration.save(update_fields=["config"])
        self.token, self.session = storage_tests.SiteFieldApiTests._session(self, {"status": "cooking", "active": True})
        self.conversation = Conversation.objects.create(
            organization=self.organization, channel=self.widget.integration.channel,
            connection=self.widget.integration, contact=self.session.identity.contact,
        )

    def update(self, fields):
        response = storage_tests.SiteFieldApiTests._fields(self, self.token, fields)
        self.assertEqual(response.status_code, 200, response.content)

    def test_enum_event_keeps_historical_labels_and_renders_for_reader(self):
        self.update({"status": "sent"})
        message = self.conversation.messages.get()
        self.assertEqual(message.system_event, SystemEvent.SITE_FIELDS_UPDATED)
        self.assertEqual(message.text, "")
        self.assertEqual(message.system_params, {
            "label": "Статус заказа", "old": "Готовится", "new": "В пути", "fieldType": "enum",
        })
        with override("ru"):
            self.assertEqual(message_payload(message)["text"], "Сайт обновил данные: Статус заказа «Готовится» → «В пути»")
        with override("en"):
            self.assertEqual(message_payload(message)["text"], "The website updated data: Статус заказа “Готовится” → “В пути”")

    def test_boolean_and_clear_translate_on_read(self):
        self.update({"active": False})
        message = self.conversation.messages.get()
        with override("ru"):
            self.assertIn("«Да» → «Нет»", message_payload(message)["text"])
        with override("en"):
            self.assertIn("“Yes” → “No”", message_payload(message)["text"])
        self.update({"active": None})
        with override("en"):
            self.assertIn("“No” → “—”", message_payload(self.conversation.messages.latest("id"))["text"])
        self.update({"active": True})
        self.assertIsNone(self.conversation.messages.latest("id").system_params["old"])

    def test_unchanged_invalid_and_other_types_do_not_add_events(self):
        previous = ContactFieldValue.objects.get(contact=self.session.identity.contact, key="status")
        self.update({"status": "cooking", "active": True, "number": "10482", "name": "Visitor"})
        self.update({"status": "unknown", "active": "yes", "missing": True})
        self.update({"number": None})
        self.assertFalse(self.conversation.messages.exists())
        self.assertEqual(ContactFieldValue.objects.get(pk=previous.pk).updated_at, previous.updated_at)

    def test_closed_dialog_and_initial_session_do_not_add_events(self):
        self.assertFalse(Message.objects.exists())
        self.conversation.lifecycle = LifecycleState.CLOSED
        self.conversation.save(update_fields=["lifecycle"])
        self.update({"status": "sent", "active": False})
        self.assertFalse(self.conversation.messages.exists())

    def test_each_open_dialog_of_contact_gets_event(self):
        other = Conversation.objects.create(
            organization=self.organization, channel=self.widget.integration.channel,
            connection=self.widget.integration, contact=self.session.identity.contact,
        )
        self.update({"status": "sent"})
        self.assertEqual(set(Message.objects.values_list("conversation_id", flat=True)), {self.conversation.id, other.id})

    def test_batch_notifies_after_commit_and_rollback_does_not_notify(self):
        with patch("chatballs.webchat.site_field_events.notify_conversation_changed") as notify:
            with self.captureOnCommitCallbacks(execute=True):
                self.update({"status": "sent", "active": False, "number": "10482"})
                notify.assert_not_called()
            notify.assert_called_once_with(self.conversation.id, organization_id=self.organization.id)
            notify.reset_mock()
            with self.captureOnCommitCallbacks(execute=True):
                self.update({"status": "sent"})
            notify.assert_not_called()
            with self.captureOnCommitCallbacks(execute=True):
                try:
                    with transaction.atomic():
                        save_site_fields(self.session, {"status": "cooking"})
                        raise ValueError("rollback")
                except ValueError:
                    pass
            notify.assert_not_called()
        self.assertEqual(self.conversation.messages.count(), 2)

    def test_string_change_notifies_without_feed_event(self):
        with patch("chatballs.webchat.site_field_events.notify_conversation_changed") as notify:
            with self.captureOnCommitCallbacks(execute=True):
                self.update({"number": "10482"})
            notify.assert_called_once()
        self.assertFalse(self.conversation.messages.exists())

    def test_site_field_events_are_not_sent_to_customer_widget(self):
        self.update({"status": "sent"})
        self.assertTrue(self.conversation.messages.exists())
        self.assertEqual(messages_payload(self.session, 0)["messages"], [])

    def test_site_field_event_does_not_clear_unread_customer_message(self):
        Message.objects.create(conversation=self.conversation, author_type=MessageAuthor.CONTACT, text="Hello")
        self.update({"status": "sent"})
        self.assertEqual(_pending_count(self.conversation), 1)
        self.assertEqual(pending_counts_for([self.conversation.id], {}), {self.conversation.id: 1})

    def test_dialog_and_contact_api_follow_current_schema(self):
        self.update({"number": "10482", "email": "visitor@example.test"})
        user = HumanUser.objects.create_user(email="reader@example.test", ui_language="en")
        OrganizationMembership.objects.create(user=user, organization=self.organization, role=EmployeeRole.ADMIN)
        client = TenantAPIClient()
        client.force_authenticate(user)
        conversation_url = f"/api/v1/conversations/{self.conversation.id}/"
        contact_url = f"/api/v1/conversations/clients/{self.session.identity.contact_id}/"
        for url, wrapper in [(conversation_url, "conversation"), (contact_url, "client")]:
            response = client.get(url)
            self.assertEqual(response.status_code, 200, response.content)
            fields = response.json()[wrapper]["siteFields"]
            self.assertEqual([item["key"] for item in fields], ["active", "status", "number"])
            self.assertEqual(fields[0]["display"], "Yes")
            self.assertEqual(fields[1]["display"], "Готовится")
            self.assertEqual(fields[1]["color"], "orange")
            self.assertEqual(set(fields[0]), {"key", "label", "type", "value", "display", "updatedAt"})
        self.widget.integration.config = {"fields": [FIELDS[0]]}
        self.widget.integration.save(update_fields=["config"])
        self.assertEqual([item["key"] for item in client.get(conversation_url).json()["conversation"]["siteFields"]], ["status"])
        self.assertEqual([item["key"] for item in client.get(contact_url).json()["client"]["siteFields"]], ["status"])
        self.assertTrue(ContactFieldValue.objects.filter(contact=self.session.identity.contact, key="number").exists())
