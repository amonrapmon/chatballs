from django.core.cache import cache
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from chatballs.channels.models import Channel
from chatballs.conversations.models import Contact, ContactFieldValue
from chatballs.identity.models import Organization
from chatballs.tenancy.database import tenant_atomic
from chatballs.webchat.models import WebSession
from chatballs.webchat.testing import create_web_widget

FIELDS = [
    {"key": "order_status", "type": "enum", "ai_access": "open",
     "options": [{"value": "cooking", "label": "Готовится"}]},
    {"key": "has_order", "type": "boolean", "ai_access": "open"},
    {"key": "user_id", "type": "string", "ai_access": "hidden"},
    {"key": "amount", "type": "number", "ai_access": "masked"},
]


class SiteFieldApiTests(TestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Site fields", slug="site-fields")
        channel = Channel.objects.create(organization=self.organization, code="site-fields", name="Site")
        self.widget = create_web_widget(channel)
        self.widget.integration.config = {"fields": FIELDS}
        self.widget.integration.save(update_fields=["config"])
        self.client = APIClient()

    def _session(self, fields=None):
        payload = {"widgetKey": self.widget.public_key}
        if fields is not None:
            payload["fields"] = fields
        response = self.client.post("/api/v1/webchat/session/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["token"], WebSession.objects.latest("id")

    def _fields(self, token, fields, **kwargs):
        return self.client.post(
            "/api/v1/webchat/fields/", {"fields": fields}, format="json",
            headers={"Authorization": f"Bearer {token}"}, **kwargs,
        )

    def test_initial_and_incremental_values_with_null_clear(self):
        token, session = self._session({"name": "Иван", "email": "ivan@example.test", "order_status": "cooking"})
        contact = session.identity.contact
        contact.refresh_from_db()
        self.assertEqual((contact.name, contact.email), ("Иван", "ivan@example.test"))
        self.assertEqual(ContactFieldValue.objects.get(contact=contact, key="order_status").value, "cooking")
        self.assertEqual(self._fields(token, {"has_order": True, "order_status": None}).status_code, 200)
        self.assertFalse(ContactFieldValue.objects.filter(contact=contact, key="order_status").exists())
        self.assertIs(ContactFieldValue.objects.get(contact=contact, key="has_order").value, True)
        self.assertEqual(self._fields(token, {"name": None, "email": None}).status_code, 200)
        contact.refresh_from_db()
        self.assertEqual((contact.name, contact.email), ("", ""))

    def test_values_are_stored_whatever_the_ai_access_mode(self):
        # Режим доступа ограничивает модель, а не сайт: скрытое от AI поле оператор видит.
        token, session = self._session()
        values = {"order_status": "cooking", "has_order": True, "user_id": "u-1", "amount": 10}
        self.assertEqual(self._fields(token, values).status_code, 200)
        stored = dict(ContactFieldValue.objects.filter(contact=session.identity.contact).values_list("key", "value"))
        self.assertEqual(stored, values)

    def test_invalid_values_are_ignored_and_not_logged(self):
        token, session = self._session()
        with self.assertLogs("chatballs.webchat.site_fields", level="WARNING") as logs:
            response = self._fields(token, {
                "unknown": "SECRET", "has_order": "SECRET", "order_status": "SECRET",
                "user_id": "SECRET" * 101,
                "amount": 10 ** 400,
            })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContactFieldValue.objects.filter(contact=session.identity.contact).exists())
        self.assertNotIn("SECRET", " ".join(logs.output))

    def test_operator_edits_are_preserved(self):
        token, session = self._session({"name": "Иван", "email": "ivan@example.test", "phone": "+79991234567"})
        contact = session.identity.contact
        Contact.objects.filter(pk=contact.pk).update(
            name="Оператор", email="manual@example.test", phone="+79990000000"
        )
        self.assertEqual(self._fields(token, {"name": "Пётр", "email": "new@example.test", "phone": "+79991111111"}).status_code, 200)
        contact.refresh_from_db()
        self.assertEqual((contact.name, contact.email, contact.phone), ("Оператор", "manual@example.test", "+79990000000"))

    def test_site_fields_do_not_identify_or_merge_visitors(self):
        fields = {"email": "same@example.test", "phone": "+79991234567", "user_id": "same"}
        _, first = self._session(fields)
        _, second = self._session(fields)
        self.assertNotEqual(first.identity.contact_id, second.identity.contact_id)
        self.assertEqual(Contact.objects.filter(organization=self.organization).count(), 2)

    def test_fields_endpoint_requires_session_and_uses_write_throttle(self):
        self.assertEqual(self.client.post("/api/v1/webchat/fields/", {"fields": {}}, format="json").status_code, 401)
        token, _ = self._session()
        original = SimpleRateThrottle.THROTTLE_RATES
        SimpleRateThrottle.THROTTLE_RATES = {**original, "webchat_session_write": "1/min"}
        cache.clear()
        try:
            self.assertEqual(self._fields(token, {}).status_code, 200)
            self.assertEqual(self._fields(token, {}, REMOTE_ADDR="203.0.113.2").status_code, 429)
        finally:
            SimpleRateThrottle.THROTTLE_RATES = original
            cache.clear()


class SiteFieldRuntimeRoleTests(TransactionTestCase):
    def test_values_are_tenant_scoped_under_app_role(self):
        first = Organization.objects.create(name="First", slug="site-fields-first")
        second = Organization.objects.create(name="Second", slug="site-fields-second")
        first_contact = None
        first_integration = None
        for organization in (first, second):
            channel = Channel.objects.create(organization=organization, code="site", name="Site")
            widget = create_web_widget(channel)
            contact = Contact.objects.create(organization=organization, name="Visitor")
            ContactFieldValue.objects.create(
                organization=organization, contact=contact, integration=widget.integration,
                key="user_id", value="private",
            )
            if organization == first:
                first_contact = contact
                first_integration = widget.integration
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE chatballs_runtime_app")
        try:
            with tenant_atomic(first.id):
                self.assertEqual(ContactFieldValue.objects.count(), 1)
                self.assertEqual(ContactFieldValue.objects.get().organization_id, first.id)
                self.assertEqual(ContactFieldValue.objects.filter(organization=second).update(value="leak"), 0)
                ContactFieldValue.objects.create(
                    organization=first, contact=first_contact, integration=first_integration,
                    key="has_order", value=True,
                )
                self.assertEqual(ContactFieldValue.objects.count(), 2)
            with tenant_atomic(second.id):
                self.assertEqual(ContactFieldValue.objects.count(), 1)
                self.assertEqual(ContactFieldValue.objects.get().organization_id, second.id)
            with transaction.atomic():
                self.assertEqual(ContactFieldValue.objects.count(), 0)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
