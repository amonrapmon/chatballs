"""Real PostgreSQL parallel workers for staged Connector media.

A single TestCase transaction would hide races. Use separate database sessions
and the runtime RLS role to exercise provider-id uniqueness and row locks.
"""
from __future__ import annotations

import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from threading import Barrier

from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings

from chatballs.api_connector.lifecycle import parse_lifecycle_event
from chatballs.api_connector.payloads import ConnectorPayloadError
from chatballs.conversations.connector_media import apply_media_lifecycle
from chatballs.conversations.connector_media_models import ConnectorMediaIngest
from chatballs.conversations.models import Message
from chatballs.events.models import InboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import system_tenant_context

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC"
)


class ConnectorMediaConcurrencyTests(TransactionTestCase):
    def setUp(self):
        owner = bootstrap_owner(
            email="media-concurrency@example.com", password="Temporary-Password-2026!",
        )
        self.org = owner.organization
        self.integration = create_integration(
            context=system_tenant_context(self.org),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR,
                name="Concurrent staged media",
                config={"connectorService": "custom_adapter"},
            ),
        )
        self.integration.config = {
            **self.integration.config,
            "connectorMediaInboundEnabled": True,
            "connectorMediaLifecycleEnabled": True,
        }
        self.integration.save(update_fields=["config"])
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        settings_override = override_settings(MEDIA_ROOT=temp.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)

    def event(self, phase: str, *, eid: str | None = None):
        event = {
            "schema": "chatballs.api-connector.event.v1",
            "source_id": f"connection-{self.integration.id}",
            "event": {
                "id": eid or f"parallel-{phase}",
                "type": f"message.media.{phase}",
                "occurred_at": "2026-11-03T12:00:00Z",
            },
            "conversation": {"external_chat_id": "concurrent-guest"},
            "media": {"external_message_id": "one-photo", "part_index": 0},
        }
        if phase == "announced":
            event["sender"] = {"external_user_id": "guest-42", "display_name": "Guest"}
            event["media"].update({"kind": "image", "caption": ""})
        elif phase == "ready":
            event["media"]["manifest"] = {
                "filename": "photo.png",
                "content_type": "image/png",
                "size_bytes": len(PNG),
                "sha256": hashlib.sha256(PNG).hexdigest(),
            }
            return parse_lifecycle_event(
                event, file_bytes=PNG, filename="photo.png", content_type="image/png",
            )
        else:
            event["media"].update({"reason": "PROVIDER_QUOTA", "retryable": True})
        return parse_lifecycle_event(event)

    def race(self, events):
        barrier = Barrier(2)

        def execute(event):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET ROLE chatballs_runtime_app")
                barrier.wait(timeout=10)
                try:
                    with tenant_atomic(self.org.id):
                        apply_media_lifecycle(self.integration, event)
                    return 202
                except ConnectorPayloadError as error:
                    return error.status
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(execute, event) for event in events]
            return [future.result(timeout=30) for future in futures]

    def test_concurrent_announcements_create_one_native_message(self):
        event = self.event("announced")
        self.assertEqual(self.race([event, event]), [202, 202])
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(ConnectorMediaIngest.objects.count(), 1)
        self.assertEqual(InboxEvent.objects.count(), 1)

    def test_concurrent_conflicting_provider_identity_is_rejected(self):
        first = self.event("announced")
        conflicting = self.event("announced", eid="parallel-other-announce")
        self.assertCountEqual(self.race([first, conflicting]), [202, 409])
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(ConnectorMediaIngest.objects.count(), 1)
        self.assertEqual(InboxEvent.objects.count(), 1)

    def test_concurrent_ready_replay_writes_exactly_one_blob(self):
        with tenant_atomic(self.org.id):
            apply_media_lifecycle(self.integration, self.event("announced"))
        ready = self.event("ready")
        self.assertEqual(self.race([ready, ready]), [202, 202])
        message = Message.objects.get()
        self.assertEqual(message.connector_media["status"], "READY")
        self.assertEqual(message.connector_media["revision"], 2)
        self.assertEqual(InboxEvent.objects.count(), 2)
        with tenant_atomic(self.org.id):
            folder = f"organizations/{self.org.public_id}/connector-media/{message.pk}"
            _, files = message.attachment.storage.listdir(folder)
            self.assertEqual(len(files), 1)

    def test_ready_and_failed_race_never_regresses_ready(self):
        with tenant_atomic(self.org.id):
            apply_media_lifecycle(self.integration, self.event("announced"))
        self.assertEqual(self.race([self.event("ready"), self.event("failed")]), [202, 202])
        message = Message.objects.get()
        self.assertEqual(message.connector_media["status"], "READY")
        self.assertTrue(message.attachment)
        self.assertEqual(Message.objects.count(), 1)
