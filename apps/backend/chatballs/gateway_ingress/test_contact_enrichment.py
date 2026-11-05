"""Focused Gateway phone enrichment tests (no bot/contact-share changes)."""

from __future__ import annotations

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from chatballs.channels.models import Channel
from chatballs.conversations.contacts_merge import merge_contacts
from chatballs.conversations.models import ConnectionIdentity, Contact, Message, MessageKind
from chatballs.gateway_ingress.contact_enrichment import normalize_provider_phone
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider


class ProviderPhoneNormalizationTests(SimpleTestCase):
    def test_normalizes_russian_and_international_numbers(self) -> None:
        self.assertEqual(normalize_provider_phone("79991234567"), "+79991234567")
        self.assertEqual(normalize_provider_phone("8 (999) 123-45-67"), "+79991234567")
        self.assertEqual(normalize_provider_phone("+7 (999) 123-45-67"), "+79991234567")
        self.assertEqual(normalize_provider_phone("+4917612345678"), "+4917612345678")

    def test_ignores_hidden_or_invalid_numbers(self) -> None:
        for candidate in ("", "0", " 0 ", "00000000000", "123", "+7abc999", "no phone"):
            with self.subTest(candidate=candidate):
                self.assertEqual(normalize_provider_phone(candidate), "")


class GatewayContactEnrichmentTests(TestCase):
    def setUp(self) -> None:
        result = bootstrap_owner(email="phone-enrichment@example.com", password="Test-Password-2026!")
        self.organization = result.organization
        self.owner = result.owner
        self.channel = Channel.objects.create(
            organization=self.organization,
            code="phone-enrichment",
            name="Gateway phone enrichment",
        )
        self.integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.GATEWAY,
            name="Gateway phone source",
            secret="gateway-phone-secret",
            config={"source_id": "max-main", "base_url": "https://gateway.example.test/"},
            channel=self.channel,
        )
        self.client = APIClient()

    def _post(self, phone: str | None, *, event_id: str = "event-1", message_id: str = "message-1"):
        payload = {
            "schema": "intercom-gw.chatballs.inbound.v1",
            "source_id": "max-main",
            "event_id": event_id,
            "occurred_at": "2026-10-21T12:00:00Z",
            "chat": {"external_chat_id": "chat-1", "type": "personal"},
            "sender": {
                "external_user_id": "user-1",
                "display_name": "Анна",
                "username": "anna",
                "phone": phone,
                "avatar_url": None,
            },
            "message": {
                "external_message_id": message_id,
                "reply_to_message_id": None,
                "text": "Здравствуйте",
            },
        }
        return self.client.post(
            f"/api/v1/gateway/integrations/{self.integration.id}/inbound/",
            data=payload,
            format="json",
            HTTP_AUTHORIZATION="Bearer gateway-phone-secret",
        )

    def _contact(self) -> Contact:
        return ConnectionIdentity.objects.get(
            connection=self.integration,
            external_user_id="user-1",
        ).contact

    def test_new_contact_receives_phone_without_verification_or_ack(self) -> None:
        self.assertEqual(self._post("79991234567").status_code, 202)

        identity = ConnectionIdentity.objects.get(connection=self.integration, external_user_id="user-1")
        self.assertEqual(identity.contact.phone, "+79991234567")
        self.assertIsNone(identity.phone_verified_at)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(Message.objects.get().kind, MessageKind.TEXT)

    def test_existing_contact_without_phone_is_enriched(self) -> None:
        self.assertEqual(self._post(None).status_code, 202)
        self.assertEqual(self._contact().phone, "")

        self.assertEqual(self._post("89991234567", event_id="event-2", message_id="message-2").status_code, 202)
        self._contact().refresh_from_db()
        self.assertEqual(self._contact().phone, "+79991234567")
        self.assertEqual(Message.objects.count(), 2)

    def test_existing_phone_is_never_overwritten(self) -> None:
        self.assertEqual(self._post(None).status_code, 202)
        contact = self._contact()
        contact.phone = "+79165554433"
        contact.save(update_fields=["phone"])

        self.assertEqual(self._post("79991234567", event_id="event-2", message_id="message-2").status_code, 202)
        contact.refresh_from_db()
        self.assertEqual(contact.phone, "+79165554433")

    def test_hidden_and_invalid_phone_values_do_not_fill_contact(self) -> None:
        for n, phone in enumerate(("0", "123", "+7INVALID", ""), start=1):
            with self.subTest(phone=phone):
                self.assertEqual(self._post(phone, event_id=f"event-{n}", message_id=f"message-{n}").status_code, 202)
        self.assertEqual(self._contact().phone, "")
        self.assertEqual(Message.objects.count(), 4)

    def test_repeat_event_does_not_duplicate_messages_or_overwrite_phone(self) -> None:
        self.assertEqual(self._post("79991234567").status_code, 202)
        self.assertEqual(self._post("79165554433").status_code, 202)
        self.assertEqual(self._contact().phone, "+79991234567")
        self.assertEqual(Message.objects.count(), 1)

    def test_merged_contact_receives_phone_on_existing_identity(self) -> None:
        self.assertEqual(self._post(None).status_code, 202)
        source = self._contact()
        target = Contact.objects.create(organization=self.organization, name="Анна")
        merge_contacts(
            organization=self.organization,
            target_id=target.id,
            source_id=source.id,
            reason="Один человек в двух каналах",
            actor=self.owner,
        )

        self.assertEqual(self._post("79991234567", event_id="event-2", message_id="message-2").status_code, 202)
        target.refresh_from_db()
        self.assertEqual(target.phone, "+79991234567")
        self.assertEqual(self._contact().id, target.id)
        self.assertEqual(Message.objects.count(), 2)
