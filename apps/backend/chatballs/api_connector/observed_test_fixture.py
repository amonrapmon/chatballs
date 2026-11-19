"""Synthetic Connector observation fixtures shared by PostgreSQL tests."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from chatballs.conversations.models import Conversation
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.testing import TenantAPIClient, system_tenant_context


class ObservedOutgoingFixture:
    def setUp(self):
        result = bootstrap_owner(
            email="connector-observed-owner@example.com",
            password="Temporary-Password-2026!",
        )
        self.organization, self.owner = result.organization, result.owner
        self.client = TenantAPIClient()
        self.client.force_login(self.owner)
        self.integration = create_integration(
            context=system_tenant_context(self.organization),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR, name="Observed adapter",
                config={"connectorService": "custom_adapter"},
            ),
        )
        credential = self.client.post(
            f"/api/v1/integrations/{self.integration.pk}/connector-credential/",
            data={}, format="json",
        )
        self.assertEqual(credential.status_code, 201)
        self.webhook = credential.data["webhookPath"]
        self.token = credential.data["token"]
        self.source = credential.data["sourceId"]
        self.cutover = timezone.now() - timedelta(minutes=2)
        self.occurred_at = self.cutover + timedelta(seconds=45)
        self.observed_at = self.occurred_at + timedelta(seconds=1)
        self.assertEqual(self.set_mirror(True).status_code, 200)

    def set_mirror(self, enabled, *, at=None, connection_id=None):
        with patch("chatballs.integrations.connector_settings.timezone.now", return_value=at or self.cutover):
            return self.client.patch(
                f"/api/v1/integrations/{connection_id or self.integration.pk}/",
                {"config": {"mirrorExternalOutgoingEnabled": enabled}}, format="json",
            )

    def send(self, payload, *, url=None, token=None):
        return self.client.post(
            url or self.webhook, payload, format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token if token is None else token}",
        )

    def incoming(self, *, event_id="in-1", external_id="guest-message-1", chat_id="chat-1"):
        return {
            "schema": "chatballs.api-connector.event.v1",
            "source_id": self.source,
            "event": {
                "id": event_id, "type": "message.created",
                "occurred_at": "2026-10-23T12:00:00Z",
            },
            "conversation": {"external_chat_id": chat_id},
            "sender": {"external_user_id": "guest-1", "display_name": "Guest"},
            "message": {
                "external_message_id": external_id,
                "direction": "inbound", "origin": "external_observed",
                "actor": "contact", "kind": "text",
                "text": "Здравствуйте", "attachments": [],
            },
        }

    def observed(self, *, event_id="observed-1", external_id="native-operator-1",
                 chat_id="chat-1", text="Ответ напрямую в мессенджере"):
        return {
            "schema": "chatballs.api-connector.event.v1",
            "source_id": self.source,
            "event": {
                "id": event_id, "type": "message.observed_outgoing",
                "occurred_at": self.occurred_at.isoformat().replace("+00:00", "Z"),
                "observed_at": self.observed_at.isoformat().replace("+00:00", "Z"),
            },
            "conversation": {"external_chat_id": chat_id},
            # Provider actor ID is untrusted metadata, never a Chatballs employee.
            "sender": {"external_user_id": "remote-admin-7", "display_name": "Someone"},
            "message": {
                "external_message_id": external_id,
                "direction": "outbound", "origin": "external_observed",
                "actor": "unknown", "kind": "text",
                "text": text, "attachments": [],
            },
        }

    def open_conversation(self, *, chat_id="chat-1", event_id="in-1"):
        self.assertEqual(
            self.send(self.incoming(chat_id=chat_id, event_id=event_id)).status_code,
            202,
        )
        return Conversation.objects.get(external_chat_id=chat_id)
