"""Operator-to-adapter text acceptance without Green API or AI."""
from __future__ import annotations

import json
from unittest.mock import patch

from django.test import TestCase

from chatballs.api_connector.outbound import (
    CONNECTOR_OUTBOUND_REQUESTED,
    deliver_connector_command,
)
from chatballs.api_connector.testing_fake_adapter import FakeAdapter
from chatballs.conversations.models import Conversation, Message
from chatballs.events.models import OutboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.tenancy.context import TenantContext
from chatballs.testing import TenantAPIClient, system_tenant_context


class _AcceptedResponse:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class APIConnectorOutboundTests(TestCase):
    def setUp(self):
        result = bootstrap_owner(
            email="connector-outbound@example.com", password="Temporary-Test-Password!",
        )
        self.org, self.owner = result.organization, result.owner
        self.client = TenantAPIClient()
        self.client.force_login(self.owner)
        self.integration = create_integration(
            context=system_tenant_context(self.org),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR, name="Independent adapter",
                config={"connectorService": "custom_adapter"},
            ),
        )
        key_response = self.client.post(
            f"/api/v1/integrations/{self.integration.pk}/connector-credential/",
            data={}, format="json",
        )
        self.assertEqual(key_response.status_code, 201)
        self.ingress_token = key_response.data["token"]
        self.webhook = key_response.data["webhookPath"]

    def event(self):
        return {
            "schema": "chatballs.api-connector.event.v1",
            "source_id": f"connection-{self.integration.pk}",
            "event": {
                "id": "evt-outbound-1", "type": "message.created",
                "occurred_at": "2026-10-23T12:00:00Z",
            },
            "conversation": {"external_chat_id": "chat-123", "thread": None},
            "sender": {"external_user_id": "user-123", "display_name": "Guest"},
            "message": {
                "external_message_id": "provider-1",
                "direction": "inbound", "origin": "external_observed",
                "actor": "contact", "kind": "text", "text": "Hello",
                "attachments": [],
            },
        }

    def make_conversation(self):
        incoming = self.client.post(
            self.webhook, self.event(), format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.ingress_token}",
        )
        self.assertEqual(incoming.status_code, 202, incoming.data)
        return Conversation.objects.get()

    def configure(self, url="http://127.0.0.1:9081/v1/commands"):
        response = self.client.post(
            f"/api/v1/integrations/{self.integration.pk}/connector-transport/",
            data={"url": url, "token": "local-fake-adapter-token-123456"}, format="json",
        )
        return response

    def test_outbound_disabled_before_configuration(self):
        conversation = self.make_conversation()
        response = self.client.post(
            f"/api/v1/conversations/{conversation.pk}/messages/",
            data={"text": "Operator reply"}, format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Message.objects.count(), 1)
        self.assertFalse(OutboxEvent.objects.filter(event_type=CONNECTOR_OUTBOUND_REQUESTED).exists())

    def test_operator_message_queued_and_accepted_with_immutable_route(self):
        conversation = self.make_conversation()
        self.assertEqual(self.configure().status_code, 200)
        reply = self.client.post(
            f"/api/v1/conversations/{conversation.pk}/messages/",
            data={"text": "Operator reply"}, format="json",
        )
        self.assertEqual(reply.status_code, 201, reply.data)
        self.assertEqual(reply.data["message"]["connectorDelivery"]["state"], "QUEUED")
        event = OutboxEvent.objects.get(event_type=CONNECTOR_OUTBOUND_REQUESTED)
        command = event.payload["command"]
        self.assertEqual(command["recipient"], {
            "external_chat_id": "chat-123", "external_user_id": "user-123",
        })
        self.assertEqual(command["message"]["text"], "Operator reply")
        self.assertNotIn("local-fake-adapter-token", json.dumps(event.payload))
        with patch("chatballs.api_connector.outbound.build_opener") as mock_opener:
            mock_opener.return_value.open.return_value = _AcceptedResponse()
            deliver_connector_command(event.payload, TenantContext.for_resource(self.org))
            first_call = mock_opener.return_value.open.call_args
            sent_request = first_call.args[0]
            self.assertEqual(
                json.loads(sent_request.data)["command_id"], command["command_id"],
            )
            self.assertEqual(
                sent_request.get_header("Authorization"),
                "Bearer local-fake-adapter-token-123456",
            )
            deliver_connector_command(event.payload, TenantContext.for_resource(self.org))
            self.assertEqual(mock_opener.return_value.open.call_count, 1)
        message = Message.objects.get(pk=reply.data["message"]["id"])
        self.assertEqual(message.connector_delivery["state"], "ADAPTER_ACCEPTED")

    def test_real_http_fake_adapter_accepts_outbox_command(self):
        """Actual HTTP + Bearer + fsynced independent receiver, no Green API."""
        with FakeAdapter(source_id=f"connection-{self.integration.pk}") as adapter:
            configured = self.configure(url=adapter.url)
            self.assertEqual(configured.status_code, 200, configured.data)
            conversation = self.make_conversation()
            reply = self.client.post(
                f"/api/v1/conversations/{conversation.pk}/messages/",
                data={"text": "Real HTTP operator reply"}, format="json",
            )
            self.assertEqual(reply.status_code, 201, reply.data)
            event = OutboxEvent.objects.get(event_type=CONNECTOR_OUTBOUND_REQUESTED)
            deliver_connector_command(event.payload, TenantContext.for_resource(self.org))
            self.assertEqual(len(adapter.commands), 1)
            self.assertEqual(
                adapter.commands[0]["message"]["text"], "Real HTTP operator reply",
            )
            self.assertEqual(adapter.commands[0]["command_id"],
                             event.payload["command"]["command_id"])
            self.assertEqual(Message.objects.get(pk=reply.data["message"]["id"])
                             .connector_delivery["state"], "ADAPTER_ACCEPTED")
            # Subsequent worker replay observes state and never sends a second command.
            deliver_connector_command(event.payload, TenantContext.for_resource(self.org))
            self.assertEqual(len(adapter.commands), 1)

    def test_adapter_failure_does_not_claim_acceptance(self):
        conversation = self.make_conversation()
        self.assertEqual(self.configure().status_code, 200)
        reply = self.client.post(
            f"/api/v1/conversations/{conversation.pk}/messages/",
            data={"text": "Retry this message"}, format="json",
        )
        event = OutboxEvent.objects.get(event_type=CONNECTOR_OUTBOUND_REQUESTED)
        with patch("chatballs.api_connector.outbound.build_opener") as opener:
            opener.return_value.open.side_effect = TimeoutError("unreachable")
            with self.assertRaisesRegex(RuntimeError, "connector_adapter_unavailable"):
                deliver_connector_command(event.payload, TenantContext.for_resource(self.org))
        self.assertEqual(
            Message.objects.get(pk=reply.data["message"]["id"]).connector_delivery["state"],
            "QUEUED",
        )

    def test_validation_and_credentials_not_exposed(self):
        for url in (
            "file:///tmp/commands", "http://example.com/v1/commands",
            "https://host.local/v1/commands?token=bad",
            "https://user:pass@host.local/v1/commands",
            "https://host.local/other",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.configure(url=url).status_code, 400)
        response = self.configure(url="https://adapter.example/v1/commands")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("local-fake-adapter-token", str(response.data))
        detail = self.client.get("/api/v1/integrations/")
        self.assertNotIn("local-fake-adapter-token", str(detail.data))
        self.integration.refresh_from_db()
        self.assertNotIn("local-fake-adapter-token", str(self.integration.config))
