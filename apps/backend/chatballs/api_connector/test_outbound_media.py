"""Operator native file -> durable Connector command -> scoped private download."""
from __future__ import annotations

import hashlib
import json
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import UUID

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from chatballs.api_connector.outbound import CONNECTOR_OUTBOUND_REQUESTED, deliver_connector_command
from chatballs.conversations.models import Conversation, Message, MessageKind
from chatballs.events.models import OutboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.tenancy.context import TenantContext
from chatballs.testing import TenantAPIClient, system_tenant_context

# Actual JPEG signature is all the Connector/M1 pilot requires at this boundary.
PHOTO = b"\xff\xd8\xff\xe0" + b"Native JPEG payload for scoped outbound test" + b"\xff\xd9"


class ConnectorNativeOutboundMediaTests(TestCase):
    def setUp(self):
        owner = bootstrap_owner(
            email="connector-file-owner@example.com",
            password="Temporary-Password-2026!",
        )
        self.org = owner.organization
        self.client = TenantAPIClient()
        self.client.force_login(owner.owner)
        self.integration = create_integration(
            context=system_tenant_context(self.org),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR, name="Operator media",
                config={"connectorService": "custom_adapter"},
            ),
        )
        response = self.client.post(
            f"/api/v1/integrations/{self.integration.id}/connector-credential/",
            data={}, format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.token = response.data["token"]
        self.webhook = response.data["webhookPath"]
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        override = override_settings(MEDIA_ROOT=directory.name)
        override.enable()
        self.addCleanup(override.disable)

    def make_conversation(self):
        event = {
            "schema": "chatballs.api-connector.event.v1",
            "source_id": f"connection-{self.integration.pk}",
            "event": {
                "id": "evt-file-outbound-1",
                "type": "message.created",
                "occurred_at": "2026-10-26T12:00:00Z",
            },
            "conversation": {"external_chat_id": "chat-1", "thread": None},
            "sender": {"external_user_id": "guest-1", "display_name": "Guest"},
            "message": {
                "external_message_id": "msg-1", "direction": "inbound",
                "origin": "external_observed", "actor": "contact",
                "kind": "text", "text": "Hello", "attachments": [],
            },
        }
        response = self.client.post(
            self.webhook, event, format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(response.status_code, 202)
        return Conversation.objects.get()

    def enable(self):
        self.integration.config = {
            **self.integration.config, "connectorMediaOutboundEnabled": True,
        }
        self.integration.save(update_fields=["config"])
        response = self.client.post(
            f"/api/v1/integrations/{self.integration.pk}/connector-transport/",
            data={"url": "http://127.0.0.1:9081/v1/commands",
                  "token": "adapter-command-token-123456789"}, format="json",
        )
        self.assertEqual(response.status_code, 200)

    def upload(self, conversation, *, data=PHOTO, name="photo.jpg", mime="image/jpeg", key=None):
        return self.client.post(
            f"/api/v1/conversations/{conversation.pk}/attachments/",
            data={
                "file": SimpleUploadedFile(name, data, content_type=mime),
                "text": "Operator file",
            },
            format="multipart",
            **({"HTTP_IDEMPOTENCY_KEY": key} if key else {}),
        )

    def private_url(self, command_id):
        return reverse("api-connector-command-attachment", kwargs={
            "connector_organization_public_id": self.org.public_id,
            "integration_id": self.integration.pk,
            "command_id": UUID(command_id),
        })

    def test_native_attachment_command_and_authenticated_read(self):
        conversation = self.make_conversation()
        self.enable()
        response = self.upload(conversation)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["message"]["connectorDelivery"]["state"], "QUEUED")
        msg = Message.objects.get(pk=response.data["message"]["id"])
        self.assertEqual(msg.kind, MessageKind.FILE)
        self.assertEqual(msg.attachment_size, len(PHOTO))
        event = OutboxEvent.objects.get(event_type=CONNECTOR_OUTBOUND_REQUESTED)
        command = event.payload["command"]
        self.assertEqual(command["recipient"]["external_chat_id"], "chat-1")
        self.assertEqual(command["message"]["kind"], "file")
        self.assertEqual(command["message"]["text"], "Operator file")
        manifest = command["message"]["media"][0]
        self.assertEqual(manifest["ref"], "command")
        self.assertEqual(manifest["filename"], "photo.jpg")
        self.assertEqual(manifest["size_bytes"], len(PHOTO))
        self.assertEqual(manifest["sha256"], hashlib.sha256(PHOTO).hexdigest())
        self.assertNotIn("adapter-command-token", json.dumps(event.payload))
        self.assertNotIn(self.token, json.dumps(event.payload))
        self.assertNotIn("http", json.dumps(command["message"]))

        url = self.private_url(command["command_id"])
        denied = self.client.get(url, HTTP_AUTHORIZATION="Bearer wrong")
        self.assertEqual(denied.status_code, 401)
        granted = self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {self.token}")
        self.assertEqual(granted.status_code, 200)
        self.assertEqual(b"".join(granted.streaming_content), PHOTO)
        self.assertIn("no-store", granted["Cache-Control"])
        self.assertEqual(granted["Content-Type"], "image/jpeg")
        bad_id = self.private_url("11111111-1111-4111-8111-111111111111")
        self.assertEqual(
            self.client.get(bad_id, HTTP_AUTHORIZATION=f"Bearer {self.token}").status_code,
            404,
        )

        with patch("chatballs.api_connector.outbound.build_opener") as mock_opener:
            mock_opener.return_value.open.side_effect = TimeoutError("offline")
            with self.assertRaisesRegex(RuntimeError, "connector_adapter_unavailable"):
                deliver_connector_command(event.payload, TenantContext.for_resource(self.org))
        msg.refresh_from_db()
        self.assertEqual(msg.connector_delivery["state"], "QUEUED")

    def test_disabled_or_invalid_file_creates_no_operator_outbox(self):
        conversation = self.make_conversation()
        disabled = self.upload(conversation)
        self.assertEqual(disabled.status_code, 400)
        self.assertFalse(OutboxEvent.objects.filter(event_type=CONNECTOR_OUTBOUND_REQUESTED).exists())
        self.enable()
        for data, name, mime in [
            (b"not-jpeg", "photo.jpg", "image/jpeg"),
            (PHOTO, "photo.gif", "image/gif"),
            (b"%PDF-1.7", "photo.jpg", "image/jpeg"),
        ]:
            with self.subTest(name=name, data=data):
                rejected = self.upload(conversation, data=data, name=name, mime=mime)
                self.assertEqual(rejected.status_code, 400)
        self.assertFalse(OutboxEvent.objects.filter(event_type=CONNECTOR_OUTBOUND_REQUESTED).exists())

    def test_idempotent_operator_replay_keeps_one_file_command(self):
        conversation = self.make_conversation()
        self.enable()
        key = "9abc9a22-ce33-41b9-8300-91d85787b412"
        first = self.upload(conversation, key=key)
        self.assertEqual(first.status_code, 201, first.data)
        replay = self.upload(conversation, key=key)
        self.assertEqual(replay.status_code, 201, replay.data)
        self.assertEqual(first.data["message"]["id"], replay.data["message"]["id"])
        self.assertEqual(
            OutboxEvent.objects.filter(event_type=CONNECTOR_OUTBOUND_REQUESTED).count(), 1,
        )
