"""Staged inbound media: one visible Message even when provider bytes fail.

These tests exercise the actual authenticated, tenant-scoped HTTP webhook,
PostgreSQL uniqueness, native file storage and existing unread/queue semantics.
"""
from __future__ import annotations

import base64
import hashlib
import json
from tempfile import TemporaryDirectory
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from chatballs.conversations.connector_media_models import ConnectorMediaIngest
from chatballs.conversations.models import Conversation, Message, MessageKind
from chatballs.conversations.serializers import message_payload
from chatballs.events.models import InboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient, system_tenant_context

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
)


class ConnectorMediaLifecycleTests(TestCase):
    def setUp(self):
        owner = bootstrap_owner(
            email="media-lifecycle@example.com", password="Temporary-Password-2026!",
        )
        self.org = owner.organization
        self.client = TenantAPIClient()
        self.client.force_login(owner.owner)
        self.integration = create_integration(
            context=system_tenant_context(self.org),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR,
                name="Staged media", config={"connectorService": "custom_adapter"},
            ),
        )
        credential = self.client.post(
            f"/api/v1/integrations/{self.integration.id}/connector-credential/",
            {}, format="json",
        )
        self.assertEqual(credential.status_code, 201)
        self.token = credential.data["token"]
        self.source = credential.data["sourceId"]
        self.url = reverse("api-connector-events", kwargs={
            "connector_organization_public_id": self.org.public_id,
            "integration_id": self.integration.id,
        })
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        override = override_settings(MEDIA_ROOT=temp.name)
        override.enable()
        self.addCleanup(override.disable)

    def enable(self):
        self.integration.config = {
            **self.integration.config,
            "connectorMediaInboundEnabled": True,
            "connectorMediaLifecycleEnabled": True,
        }
        self.integration.save(update_fields=["config"])

    def event(self, phase, *, kind="image", eid=None, mid="provider-photo-1", caption=""):
        suffix = {"announced": "announce", "ready": "ready", "failed": "failed"}[phase]
        envelope = {
            "schema": "chatballs.api-connector.event.v1",
            "source_id": self.source,
            "event": {
                "id": eid or f"evt-{suffix}-1",
                "type": f"message.media.{phase}",
                "occurred_at": "2026-11-03T12:00:00Z",
            },
            "conversation": {"external_chat_id": "private-42"},
            "media": {"external_message_id": mid, "part_index": 0},
        }
        if phase == "announced":
            envelope["sender"] = {
                "external_user_id": "guest-42", "display_name": "Test guest",
            }
            envelope["media"].update({"kind": kind, "caption": caption})
        elif phase == "ready":
            envelope["media"]["manifest"] = {
                "filename": "photo.png", "content_type": "image/png",
                "size_bytes": len(PNG), "sha256": hashlib.sha256(PNG).hexdigest(),
            }
        elif phase == "failed":
            envelope["media"].update({"reason": "PROVIDER_QUOTA", "retryable": True})
        return envelope

    def send(self, payload, *, binary=False, token=None, url=None):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {self.token if token is None else token}"}
        if binary:
            return self.client.post(
                url or self.url, {
                    "event": json.dumps(payload),
                    "file": SimpleUploadedFile("photo.png", PNG, content_type="image/png"),
                }, format="multipart", **headers,
            )
        return self.client.post(url or self.url, payload, format="json", **headers)

    def test_announce_is_visible_and_ready_updates_same_native_message(self):
        self.enable()
        announce = self.event("announced")
        first = self.send(announce)
        self.assertEqual(first.status_code, 202, first.data)
        self.assertEqual(self.send(announce).status_code, 202)
        self.assertEqual(Message.objects.count(), 1)
        message = Message.objects.get()
        initial_id = message.pk
        self.assertEqual(message.kind, MessageKind.FILE)
        self.assertEqual(message.connector_media["status"], "PENDING")
        self.assertEqual(message_payload(message)["mediaStatus"], "PENDING")
        self.assertIsNone(message_payload(message)["attachmentUrl"])
        self.assertEqual(ConnectorMediaIngest.objects.count(), 1)

        failed = self.send(self.event("failed"))
        self.assertEqual(failed.status_code, 202, failed.data)
        message.refresh_from_db()
        self.assertEqual(message.connector_media["status"], "FAILED")
        self.assertEqual(message.connector_media["reason"], "PROVIDER_QUOTA")
        self.assertEqual(message.connector_media["revision"], 2)
        self.assertEqual(self.send(self.event("failed")).status_code, 202)
        message.refresh_from_db()
        self.assertEqual(message.connector_media["revision"], 2)

        ready = self.send(self.event("ready"), binary=True)
        self.assertEqual(ready.status_code, 202, ready.data)
        message.refresh_from_db()
        self.assertEqual(message.pk, initial_id)
        self.assertEqual(message.connector_media["status"], "READY")
        self.assertEqual(message.connector_media["revision"], 3)
        self.assertEqual(message.attachment_size, len(PNG))
        with tenant_atomic(self.org.id):
            with message.attachment.open("rb") as stream:
                self.assertEqual(stream.read(), PNG)
        self.assertEqual(self.send(self.event("ready"), binary=True).status_code, 202)
        self.assertEqual(Message.objects.count(), 1)
        message.refresh_from_db()
        self.assertEqual(message.connector_media["revision"], 3)
        self.assertEqual(InboxEvent.objects.count(), 3)

        late = self.event("failed", eid="evt-late-failed")
        self.assertEqual(self.send(late).status_code, 202)
        message.refresh_from_db()
        self.assertEqual(message.connector_media["status"], "READY")
        self.assertEqual(message.connector_media["revision"], 3)

    def test_caption_is_in_same_file_message(self):
        self.enable()
        self.assertEqual(self.send(self.event("announced", caption="A real caption")).status_code, 202)
        self.assertEqual(Message.objects.count(), 1)
        message = Message.objects.get()
        self.assertEqual(message.text, "A real caption")
        self.assertEqual(message.kind, MessageKind.FILE)

    def test_unknown_media_and_source_are_fail_closed_without_consuming_event(self):
        self.enable()
        ready = self.event("ready")
        unknown = self.send(ready, binary=True)
        self.assertEqual(unknown.status_code, 409, unknown.data)
        self.assertEqual(unknown.data["error"], "unknown_media")
        self.assertEqual(InboxEvent.objects.count(), 0)
        bad = self.event("announced")
        bad["source_id"] = "connection-999999"
        self.assertEqual(self.send(bad).status_code, 409)
        self.assertEqual(Message.objects.count(), 0)
        self.assertEqual(self.send(self.event("announced")).status_code, 202)
        self.assertEqual(self.send(ready, binary=True).status_code, 202)

    def test_duplicate_provider_identity_with_new_event_id_conflicts(self):
        self.enable()
        original = self.event("announced")
        self.assertEqual(self.send(original).status_code, 202)
        repeat = self.event("announced", eid="different-event")
        self.assertEqual(self.send(repeat).status_code, 409)
        changed = self.event("announced", caption="different caption")
        self.assertEqual(self.send(changed).status_code, 409)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(InboxEvent.objects.count(), 1)

    def test_voice_announcement_visible_but_binary_remains_unsupported(self):
        self.enable()
        announced = self.event("announced", kind="voice", eid="voice-announce", mid="voice-1")
        self.assertEqual(self.send(announced).status_code, 202)
        message = Message.objects.get()
        self.assertEqual(message.kind, MessageKind.VOICE)
        self.assertEqual(message_payload(message)["mediaStatus"], "PENDING")
        failed = self.event("failed", mid="voice-1", eid="voice-failed")
        failed["media"]["reason"] = "UNSUPPORTED_KIND"
        failed["media"]["retryable"] = False
        self.assertEqual(self.send(failed).status_code, 202)
        message.refresh_from_db()
        self.assertEqual(message.connector_media["status"], "FAILED")
        self.assertIsNone(message_payload(message)["audioUrl"])
        ready = self.event("ready", mid="voice-1", eid="voice-ready")
        self.assertEqual(self.send(ready, binary=True).status_code, 422)
        self.assertEqual(Message.objects.count(), 1)

    def test_missing_capability_invalid_token_and_multipart_guard(self):
        self.assertEqual(self.send(self.event("announced")).status_code, 422)
        self.assertEqual(Message.objects.count(), 0)
        self.enable()
        self.assertEqual(self.send(self.event("announced"), token="wrong").status_code, 401)
        self.assertEqual(Message.objects.count(), 0)
        good = self.event("announced")
        good["media"]["part_index"] = 1
        self.assertEqual(self.send(good).status_code, 422)
        good = self.event("announced")
        good["media"]["description"] = "secret"
        self.assertEqual(self.send(good).status_code, 400)
        self.assertEqual(Message.objects.count(), 0)

    def test_storage_failure_does_not_claim_ready_and_is_retryable(self):
        self.enable()
        self.assertEqual(self.send(self.event("announced")).status_code, 202)
        ready = self.event("ready")
        with mock.patch(
            "django.db.models.fields.files.FieldFile.save",
            side_effect=OSError("synthetic storage error"),
        ):
            failed = self.send(ready, binary=True)
        self.assertEqual(failed.status_code, 503, failed.data)
        message = Message.objects.get()
        self.assertEqual(message.connector_media["status"], "PENDING")
        self.assertEqual(InboxEvent.objects.count(), 1)
        self.assertEqual(self.send(ready, binary=True).status_code, 202)

    def test_cannot_take_over_legacy_m1_message(self):
        self.enable()
        legacy = {
            "schema": "chatballs.api-connector.event.v1", "source_id": self.source,
            "event": {"id": "legacy-1", "type": "message.created", "occurred_at": "2026-11-03T12:00:00Z"},
            "conversation": {"external_chat_id": "private-42"},
            "sender": {"external_user_id": "guest-42"},
            "message": {
                "external_message_id": "provider-photo-1",
                "direction": "inbound", "origin": "external_observed", "actor": "contact",
                "kind": "file", "text": "", "attachments": [{
                    "filename": "photo.png", "content_type": "image/png",
                    "size_bytes": len(PNG), "sha256": hashlib.sha256(PNG).hexdigest(),
                }],
            },
        }
        self.assertEqual(self.send(legacy, binary=True).status_code, 202)
        self.assertEqual(self.send(self.event("announced")).status_code, 409)
        self.assertEqual(Message.objects.count(), 1)
