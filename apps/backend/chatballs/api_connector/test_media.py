"""Narrow native-media Connector regressions (synthetic bytes, no provider network)."""
from __future__ import annotations

import base64
import hashlib
import json
from tempfile import TemporaryDirectory
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from chatballs.conversations.models import Message, MessageKind
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


class ConnectorNativeMediaTests(TestCase):
    def setUp(self):
        result = bootstrap_owner(
            email="connector-media-owner@example.com", password="Temporary-Password-2026!",
        )
        self.org = result.organization
        self.client = TenantAPIClient()
        self.client.force_login(result.owner)
        self.integration = create_integration(
            context=system_tenant_context(self.org),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR,
                name="Media adapter", config={"connectorService": "custom_adapter"},
            ),
        )
        path = f"/api/v1/integrations/{self.integration.id}/connector-credential/"
        credential = self.client.post(path, data={}, format="json")
        self.assertEqual(credential.status_code, 201)
        self.token = credential.data["token"]
        self.source = credential.data["sourceId"]
        self.url = reverse("api-connector-events", kwargs={
            "connector_organization_public_id": self.org.public_id,
            "integration_id": self.integration.id,
        })
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        override = override_settings(MEDIA_ROOT=self.temp.name)
        override.enable()
        self.addCleanup(override.disable)

    def enable_media(self):
        self.integration.config = {
            **self.integration.config, "connectorMediaInboundEnabled": True,
        }
        self.integration.save(update_fields=["config"])

    def event(self, *, data=PNG, event_id="evt-photo-1", caption="Here's a photo"):
        return {
            "schema": "chatballs.api-connector.event.v1",
            "source_id": self.source,
            "event": {"id": event_id, "type": "message.created", "occurred_at": "2026-10-25T12:00:00Z"},
            "conversation": {"external_chat_id": "remote-chat-5", "thread": None},
            "sender": {"external_user_id": "user-5", "display_name": "Guest", "username": None, "avatar_ref": None},
            "message": {
                "external_message_id": "provider-photo-1", "direction": "inbound",
                "origin": "external_observed", "actor": "contact", "kind": "file",
                "text": caption, "attachments": [{
                    "filename": "photo.png", "content_type": "image/png",
                    "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                }],
                "html": None, "contact_share": None, "reply_to_external_message_id": None,
            },
        }

    def post_media(self, event=None, *, data=PNG, token=None, file_name="photo.png", content_type="image/png", url=None):
        return self.client.post(
            url or self.url,
            data={
                "event": json.dumps(event if event is not None else self.event(data=data)),
                "file": SimpleUploadedFile(file_name, data, content_type=content_type),
            },
            format="multipart",
            HTTP_AUTHORIZATION=f"Bearer {self.token if token is None else token}",
        )

    def test_native_image_and_caption_and_idempotent_replay(self):
        self.enable_media()
        first = self.post_media()
        self.assertEqual(first.status_code, 202, first.data)
        again = self.post_media()
        self.assertEqual(again.status_code, 202, again.data)
        self.assertEqual(InboxEvent.objects.count(), 1)
        messages = list(Message.objects.order_by("id"))
        self.assertEqual([m.kind for m in messages], [MessageKind.TEXT, MessageKind.FILE])
        self.assertEqual(messages[0].text, "Here's a photo")
        self.assertEqual(messages[1].attachment_name, "photo.png")
        self.assertEqual(messages[1].attachment_size, len(PNG))
        with tenant_atomic(self.org.id):
            with messages[1].attachment.open("rb") as stored:
                self.assertEqual(stored.read(), PNG)

    def test_pdf_as_native_file_message(self):
        self.enable_media()
        pdf = b"%PDF-1.4\n1 0 obj\nendobj\n%%EOF\n"
        event = self.event(data=pdf, event_id="pdf-1", caption="")
        event["message"]["attachments"][0].update({
            "filename": "document.pdf", "content_type": "application/pdf",
        })
        response = self.post_media(
            event, data=pdf, file_name="document.pdf", content_type="application/pdf",
        )
        self.assertEqual(response.status_code, 202, response.data)
        message = Message.objects.get()
        self.assertEqual(message.kind, MessageKind.FILE)
        self.assertEqual(message.attachment_content_type, "application/pdf")

    def test_no_caption_one_file_without_text_placeholder(self):
        self.enable_media()
        response = self.post_media(self.event(caption=""))
        self.assertEqual(response.status_code, 202, response.data)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(Message.objects.get().kind, MessageKind.FILE)

    def test_changed_manifest_or_caption_conflicts_with_existing_event(self):
        self.enable_media()
        self.assertEqual(self.post_media().status_code, 202)
        other = self.event(data=PNG + b"diff")
        self.assertEqual(self.post_media(other, data=PNG + b"diff").status_code, 409)
        with_caption = self.event(caption="Changed caption")
        self.assertEqual(self.post_media(with_caption).status_code, 409)
        self.assertEqual(Message.objects.count(), 2)

    def test_bad_bytes_size_and_manifest_are_rejected_before_ingest(self):
        self.enable_media()
        cases = []
        wrong_sha = self.event()
        wrong_sha["message"]["attachments"][0]["sha256"] = "0" * 64
        cases.append((wrong_sha, PNG, "photo.png"))
        wrong_size = self.event()
        wrong_size["message"]["attachments"][0]["size_bytes"] = 100
        cases.append((wrong_size, PNG, "photo.png"))
        wrong_type = self.event(data=b"not a PNG")
        cases.append((wrong_type, b"not a PNG", "photo.png"))
        traversal = self.event()
        traversal["message"]["attachments"][0]["filename"] = "../photo.png"
        cases.append((traversal, PNG, "photo.png"))
        for payload, data, name in cases:
            with self.subTest(case=payload["message"]["attachments"][0]):
                resp = self.post_media(payload, data=data, file_name=name)
                self.assertEqual(resp.status_code, 400, resp.data)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(InboxEvent.objects.count(), 0)

    def test_wrong_scope_disabled_capability_and_credential_fail_closed(self):
        self.assertEqual(self.post_media().status_code, 422)
        self.assertEqual(Message.objects.count(), 0)
        self.enable_media()
        self.assertEqual(self.post_media(token="wrong").status_code, 401)
        other = Organization.objects.create(name="Other Media", slug="other-media")
        url = reverse("api-connector-events", kwargs={
            "connector_organization_public_id": other.public_id,
            "integration_id": self.integration.id,
        })
        self.assertEqual(self.post_media(url=url).status_code, 404)
        self.assertEqual(Message.objects.count(), 0)

    def test_invalid_multipart_missing_file_and_json_file_are_not_accepted(self):
        self.enable_media()
        resp = self.client.post(
            self.url, {"event": json.dumps(self.event())}, format="multipart",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(resp.status_code, 400, resp.data)
        resp = self.client.post(
            self.url, self.event(), format="json", HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(resp.status_code, 422, resp.data)
        self.assertEqual(Message.objects.count(), 0)

    def test_native_storage_failure_is_retryable_not_202(self):
        self.enable_media()
        with mock.patch("django.db.models.fields.files.FieldFile.save", side_effect=OSError("disk unavailable")):
            failed = self.post_media()
        self.assertEqual(failed.status_code, 503, failed.data)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(InboxEvent.objects.count(), 0)
        self.assertEqual(self.post_media().status_code, 202)
        self.assertEqual(Message.objects.count(), 2)

    def test_existing_json_text_still_works_with_media_enabled(self):
        self.enable_media()
        payload = self.event()
        payload["message"]["kind"] = "text"
        payload["message"]["text"] = "Regular text"
        payload["message"]["attachments"] = []
        reply = self.client.post(
            self.url, payload, format="json", HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(reply.status_code, 202, reply.data)
        self.assertEqual(Message.objects.count(), 1)

    def test_empty_and_oversized_media(self):
        self.enable_media()
        self.assertEqual(
            self.post_media(self.event(data=b""), data=b"").status_code, 400
        )
        huge = b"x" * (20 * 1024 * 1024 + 1)
        response = self.post_media(self.event(data=huge), data=huge)
        self.assertEqual(response.status_code, 413, response.data)
        self.assertEqual(Message.objects.count(), 0)
