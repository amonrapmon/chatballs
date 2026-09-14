"""Фото контакта из мессенджера: скачивается один раз и отдаётся со своего адреса."""

from unittest import mock

from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.contact_avatars import (
    contact_avatar_url_in,
    refresh_contact_avatar,
)
from chatballs.conversations.models import Contact
from chatballs.conversations.transports.base import InboundMessage
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.integrations.models import (
    Integration,
    IntegrationKind,
    IntegrationProvider,
)
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient as APIClient

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class ContactAvatarTests(TestCase):
    def setUp(self) -> None:
        bootstrap_owner(email="owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.channel = Channel.objects.create(
            organization=self.organization, code="line", name="Линия"
        )
        self.contact = Contact.objects.create(
            organization=self.organization, name="Иван"
        )
        self.inbound = InboundMessage(
            external_id="1",
            user_id="777",
            chat_id="777",
            text="привет",
            display_name="Иван",
        )

    def _integration(self, provider: str) -> Integration:
        return Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=provider,
            name=provider,
            secret="token",
            channel=self.channel,
        )

    def test_telegram_photo_is_asked_once_and_stored(self) -> None:
        integration = self._integration(IntegrationProvider.TELEGRAM)
        with mock.patch(
            "chatballs.conversations.transports.telegram.download_profile_photo",
            return_value=PNG,
        ) as download:
            with tenant_atomic(self.organization.id):
                refresh_contact_avatar(integration, self.inbound, self.contact)
            with tenant_atomic(self.organization.id):
                refresh_contact_avatar(integration, self.inbound, self.contact)
        self.assertEqual(download.call_count, 1)
        self.contact.refresh_from_db()
        self.assertTrue(self.contact.avatar)
        self.assertEqual(self.contact.avatar_content_type, "image/png")
        self.assertEqual(self.contact.avatar_source, "tg:777")

    def test_telegram_without_photo_is_not_asked_again(self) -> None:
        integration = self._integration(IntegrationProvider.TELEGRAM)
        with mock.patch(
            "chatballs.conversations.transports.telegram.download_profile_photo",
            return_value=None,
        ) as download:
            with tenant_atomic(self.organization.id):
                refresh_contact_avatar(integration, self.inbound, self.contact)
            with tenant_atomic(self.organization.id):
                refresh_contact_avatar(integration, self.inbound, self.contact)
        self.assertEqual(download.call_count, 1)
        self.contact.refresh_from_db()
        self.assertFalse(self.contact.avatar)

    def test_max_photo_follows_the_url_from_the_update(self) -> None:
        integration = self._integration(IntegrationProvider.MAX)
        inbound = InboundMessage(
            external_id="1",
            user_id="777",
            chat_id="",
            text="привет",
            display_name="Иван",
            avatar_url="https://cdn.example.test/ivan.png",
        )
        with mock.patch(
            "chatballs.conversations.transports.max.download_file",
            return_value=(PNG, "image/png"),
        ) as download:
            with tenant_atomic(self.organization.id):
                refresh_contact_avatar(integration, inbound, self.contact)
            with tenant_atomic(self.organization.id):
                refresh_contact_avatar(integration, inbound, self.contact)
        self.assertEqual(download.call_count, 1)
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.avatar_source, "https://cdn.example.test/ivan.png")

    def test_download_failure_leaves_the_contact_alone(self) -> None:
        integration = self._integration(IntegrationProvider.TELEGRAM)
        with mock.patch(
            "chatballs.conversations.transports.telegram.download_profile_photo",
            side_effect=OSError("network is down"),
        ), tenant_atomic(self.organization.id):
            refresh_contact_avatar(integration, self.inbound, self.contact)
        self.contact.refresh_from_db()
        self.assertFalse(self.contact.avatar)
        self.assertEqual(self.contact.avatar_source, "")

    def test_stored_photo_is_served_from_our_own_address(self) -> None:
        integration = self._integration(IntegrationProvider.TELEGRAM)
        with mock.patch(
            "chatballs.conversations.transports.telegram.download_profile_photo",
            return_value=PNG,
        ), tenant_atomic(self.organization.id):
            refresh_contact_avatar(integration, self.inbound, self.contact)
        self.contact.refresh_from_db()
        url = contact_avatar_url_in(self.contact, self.organization.id)
        self.assertIn(f"/conversations/clients/{self.contact.id}/avatar/", url)

        client = APIClient()
        client.login(username="owner@example.com", password="temporary-password")
        response = client.get(f"/api/v1/conversations/clients/{self.contact.id}/avatar/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "image/png")
        self.assertEqual(b"".join(response.streaming_content), PNG)

    def test_contact_without_photo_has_no_url(self) -> None:
        self.assertIsNone(contact_avatar_url_in(self.contact, self.organization.id))
