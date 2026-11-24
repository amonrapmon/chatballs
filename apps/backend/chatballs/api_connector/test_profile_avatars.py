"""Binary avatar contract is provider-neutral and does not create messages."""
import base64
import hashlib
import json
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from chatballs.conversations.models import ConnectionIdentity, Contact, Message
from chatballs.events.models import InboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient, system_tenant_context

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
)


class ProfileAvatarConnectorTests(TestCase):
    def setUp(self):
        result = bootstrap_owner(
            email="profile-avatar-owner@example.com", password="Temporary-Password-2026!",
        )
        self.org = result.organization
        self.client = TenantAPIClient()
        self.client.force_login(result.owner)
        self.integration = create_integration(
            context=system_tenant_context(self.org),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR, name="Custom external connector",
                config={"connectorService": "custom_adapter"},
            ),
        )
        credential = self.client.post(
            f"/api/v1/integrations/{self.integration.pk}/connector-credential/",
            data={}, format="json",
        )
        self.assertEqual(credential.status_code, 201)
        self.token = credential.data["token"]
        self.source_id = credential.data["sourceId"]
        self.url = reverse("api-connector-events", kwargs={
            "connector_organization_public_id": self.org.public_id,
            "integration_id": self.integration.pk,
        })
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        overridden = override_settings(MEDIA_ROOT=self.temp.name)
        overridden.enable()
        self.addCleanup(overridden.disable)
        self.contact = Contact.objects.create(organization=self.org, name="Visitor")
        self.identity = ConnectionIdentity.objects.create(
            contact=self.contact, connection=self.integration,
            external_user_id="person-1", display_name="Visitor",
        )

    def enable_media(self):
        self.integration.config = {**self.integration.config, "connectorMediaInboundEnabled": True}
        self.integration.save(update_fields=["config"])

    def payload(self, *, user_id="person-1", event_id="avatar-one", content=PNG):
        return {
            "schema": "chatballs.api-connector.event.v1",
            "source_id": self.source_id,
            "event": {
                "id": event_id, "type": "contact.avatar.updated",
                "occurred_at": "2026-11-17T12:00:00Z",
            },
            "profile": {"external_user_id": user_id},
            "avatar": {
                "filename": "avatar.png", "content_type": "image/png",
                "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(),
            },
        }

    def send(self, payload=None, *, data=PNG, token=None, url=None, filename="avatar.png", mime="image/png"):
        return self.client.post(
            url or self.url,
            data={
                "event": json.dumps(payload if payload is not None else self.payload(content=data)),
                "file": SimpleUploadedFile(filename, data, content_type=mime),
            },
            format="multipart",
            HTTP_AUTHORIZATION=f"Bearer {self.token if token is None else token}",
        )

    def test_known_contact_avatar_is_stored_and_idempotent(self):
        self.enable_media()
        self.assertEqual(self.send().status_code, 202)
        self.assertEqual(self.send().status_code, 202)
        self.contact.refresh_from_db()
        self.assertTrue(self.contact.avatar.name)
        self.assertTrue(self.contact.avatar_source.startswith(f"connector:{self.integration.pk}:"))
        with tenant_atomic(self.org.pk), self.contact.avatar.open("rb") as stored:
            self.assertEqual(stored.read(), PNG)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(InboxEvent.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 1)
        self.identity.refresh_from_db()
        self.assertIsNone(self.identity.phone_verified_at)

    def test_unknown_contact_does_not_create_a_phantom_card(self):
        self.enable_media()
        self.assertEqual(self.send(self.payload(user_id="unknown")).status_code, 202)
        self.assertEqual(Contact.objects.count(), 1)
        self.contact.refresh_from_db()
        self.assertFalse(self.contact.avatar.name)
        self.assertEqual(Message.objects.count(), 0)

    def test_bad_manifest_bytes_format_and_replay_conflict(self):
        self.enable_media()
        bad = self.payload()
        bad["avatar"]["sha256"] = "0" * 64
        self.assertEqual(self.send(bad).status_code, 400)
        invalid = self.payload(content=b"not-a-png")
        self.assertEqual(self.send(invalid, data=b"not-a-png").status_code, 400)
        self.assertEqual(self.send().status_code, 202)
        changed = self.payload()
        changed["avatar"]["filename"] = "different.png"
        self.assertEqual(self.send(changed, filename="different.png").status_code, 409)
        self.assertEqual(Message.objects.count(), 0)

    def test_token_tenant_and_source_are_enforced(self):
        self.enable_media()
        self.assertEqual(self.send(token="wrong").status_code, 401)
        alien = Organization.objects.create(name="Other", slug="other-avatar")
        url = reverse("api-connector-events", kwargs={
            "connector_organization_public_id": alien.public_id,
            "integration_id": self.integration.pk,
        })
        self.assertEqual(self.send(url=url).status_code, 404)
        wrong_source = self.payload()
        wrong_source["source_id"] = "connection-99999"
        self.assertEqual(self.send(wrong_source).status_code, 409)
        self.assertEqual(Message.objects.count(), 0)

    def test_does_not_override_existing_native_or_manual_avatar(self):
        self.enable_media()
        with tenant_atomic(self.org.pk):
            self.contact.avatar.save("manual.png", SimpleUploadedFile("manual.png", PNG), save=False)
            self.contact.avatar_source = "manual"
            self.contact.save(update_fields=["avatar", "avatar_source"])
        previous = self.contact.avatar.name
        self.assertEqual(self.send().status_code, 202)
        self.contact.refresh_from_db()
        self.assertEqual(self.contact.avatar.name, previous)
        self.assertEqual(self.contact.avatar_source, "manual")

    def test_avatar_upload_requires_existing_media_opt_in(self):
        response = self.send()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(InboxEvent.objects.count(), 0)
