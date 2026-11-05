"""Authenticated delivery receipts, idempotency and monotonic state projection."""
from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

from django.test import TestCase

from chatballs.api_connector.outbound import CONNECTOR_OUTBOUND_REQUESTED, deliver_connector_command
from chatballs.conversations.models import Conversation, Message
from chatballs.events.models import InboxEvent, OutboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.tenancy.context import TenantContext
from chatballs.testing import TenantAPIClient, system_tenant_context


class APIConnectorReceiptTests(TestCase):
    def setUp(self):
        result = bootstrap_owner(
            email="connector-receipts@example.com", password="Temporary-Test-Password!",
        )
        self.org, self.owner = result.organization, result.owner
        self.client = TenantAPIClient()
        self.client.force_login(self.owner)
        self.integration = create_integration(
            context=system_tenant_context(self.org),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR, name="Receipt adapter",
                config={"connectorService": "custom_adapter"},
            ),
        )
        credential = self.client.post(
            f"/api/v1/integrations/{self.integration.pk}/connector-credential/",
            data={}, format="json",
        )
        self.assertEqual(credential.status_code, 201)
        self.token = credential.data["token"]
        self.webhook = credential.data["webhookPath"]

    def send(self, payload, *, token=None, url=None):
        return self.client.post(
            url or self.webhook, payload, format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token if token is None else token}",
        )

    def create_reply(self):
        self.assertEqual(
            self.client.post(
                f"/api/v1/integrations/{self.integration.pk}/connector-transport/",
                data={"url": "http://127.0.0.1:9081/v1/commands",
                      "token": "receipt-test-adapter-token-1234"},
                format="json",
            ).status_code, 200,
        )
        incoming = {
            "schema": "chatballs.api-connector.event.v1",
            "source_id": f"connection-{self.integration.pk}",
            "event": {
                "id": "evt-receipt-inbound", "type": "message.created",
                "occurred_at": "2026-10-23T12:00:00Z",
            },
            "conversation": {"external_chat_id": "chat-1", "thread": None},
            "sender": {"external_user_id": "user-1", "display_name": "Guest"},
            "message": {
                "external_message_id": "inbound-1",
                "direction": "inbound", "origin": "external_observed",
                "actor": "contact", "kind": "text", "text": "Hello",
                "attachments": [],
            },
        }
        self.assertEqual(self.send(incoming).status_code, 202)
        conversation = Conversation.objects.get()
        response = self.client.post(
            f"/api/v1/conversations/{conversation.pk}/messages/",
            data={"text": "Operator reply"}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        message = Message.objects.get(pk=response.data["message"]["id"])
        event = OutboxEvent.objects.get(event_type=CONNECTOR_OUTBOUND_REQUESTED)
        self.assertEqual(message.connector_delivery["state"], "QUEUED")
        return message, event

    def receipt(self, command_id, status, *, event_id="receipt-1", **extra):
        payload = {
            "schema": "chatballs.api-connector.receipt.v1",
            "source_id": f"connection-{self.integration.pk}",
            "event": {"id": event_id, "occurred_at": "2026-10-23T12:01:00Z"},
            "command_id": command_id,
            "status": status,
        }
        payload.update(extra)
        return payload

    def state(self, message):
        message.refresh_from_db()
        return message.connector_delivery

    def test_provider_sent_delivered_and_late_out_of_order_never_downgrade(self):
        message, _ = self.create_reply()
        command_id = self.state(message)["commandId"]
        sent = self.receipt(command_id, "PROVIDER_SENT", provider_message_id="provider-22")
        result = self.send(sent)
        self.assertEqual(result.status_code, 202, result.data)
        self.assertEqual(self.state(message)["state"], "PROVIDER_SENT")
        self.assertEqual(self.state(message)["providerMessageId"], "provider-22")

        delivered = self.receipt(command_id, "DELIVERED", event_id="receipt-2")
        self.assertEqual(self.send(delivered).status_code, 202)
        self.assertEqual(self.state(message)["state"], "DELIVERED")

        old = self.receipt(command_id, "PROVIDER_SENT", event_id="receipt-3")
        self.assertEqual(self.send(old).status_code, 202)
        self.assertEqual(self.state(message)["state"], "DELIVERED")
        self.assertEqual(self.send(delivered).status_code, 202)
        self.assertEqual(self.state(message)["state"], "DELIVERED")
        self.assertEqual(InboxEvent.objects.filter(source=f"api_connector_receipt:{self.integration.pk}").count(), 3)

        conflict = deepcopy(delivered)
        conflict["provider_message_id"] = "different"
        self.assertEqual(self.send(conflict).status_code, 409)
        self.assertEqual(self.state(message)["state"], "DELIVERED")

        history = self.client.get(f"/api/v1/conversations/{message.conversation_id}/messages/")
        self.assertEqual(history.status_code, 200)
        messages = history.data["items"]
        matched = next(item for item in messages if item["id"] == message.pk)
        self.assertEqual(matched["connectorDelivery"]["state"], "DELIVERED")

    def test_failed_is_terminal_and_sanitized(self):
        message, _ = self.create_reply()
        command_id = self.state(message)["commandId"]
        failed = self.receipt(
            command_id, "FAILED", failure_code="recipient_unavailable",
        )
        self.assertEqual(self.send(failed).status_code, 202)
        self.assertEqual(self.state(message)["state"], "FAILED")
        self.assertEqual(self.state(message)["failureCode"], "recipient_unavailable")
        self.assertEqual(
            self.send(self.receipt(command_id, "DELIVERED", event_id="later")).status_code,
            202,
        )
        self.assertEqual(self.state(message)["state"], "FAILED")

    def test_authenticated_source_scoped_and_unknown_command_is_retryable(self):
        message, _ = self.create_reply()
        cid = self.state(message)["commandId"]
        candidate = self.receipt(cid, "DELIVERED")
        self.assertEqual(self.send(candidate, token="wrong-token").status_code, 401)
        wrong_source = {**candidate, "source_id": "connection-99999"}
        self.assertEqual(self.send(wrong_source).status_code, 409)
        unknown = {**candidate, "command_id": "11111111-1111-4111-8111-111111111111"}
        self.assertEqual(self.send(unknown).status_code, 409)
        self.assertEqual(
            InboxEvent.objects.filter(source=f"api_connector_receipt:{self.integration.pk}").count(), 0,
        )
        self.assertEqual(self.send(candidate).status_code, 202)
        self.assertEqual(self.state(message)["state"], "DELIVERED")

    def test_invalid_receipts_fail_closed(self):
        message, _ = self.create_reply()
        cid = self.state(message)["commandId"]
        invalid_cases = [
            ({"status": []}, 422),
            ({"status": "READ"}, 422),
            ({"command_id": "bad"}, 400),
            ({"failure_code": "X: raw sensitive provider exception"}, 400),
            ({"status": "FAILED"}, 400),
            ({"status": "FAILED", "failure_code": "recipient unavailable"}, 400),
            ({"event": {"id": "receipt-1", "occurred_at": "not-a-date"}}, 400),
            ({"provider_message_id": ["bad"]}, 400),
            ({"unknown": "field"}, 400),
        ]
        for patch_data, expected in invalid_cases:
            with self.subTest(patch=patch_data):
                candidate = self.receipt(cid, "DELIVERED")
                candidate.update(patch_data)
                self.assertEqual(self.send(candidate).status_code, expected)
        self.assertEqual(self.state(message)["state"], "QUEUED")

    def test_adapter_ack_race_cannot_overwrite_provider_receipt(self):
        message, event = self.create_reply()
        cid = self.state(message)["commandId"]
        def send_then_receipt(url, token, command):
            self.assertEqual(command["command_id"], cid)
            self.assertEqual(
                self.send(self.receipt(cid, "DELIVERED")).status_code, 202,
            )
        with patch("chatballs.api_connector.outbound._send_command", side_effect=send_then_receipt):
            deliver_connector_command(event.payload, TenantContext.for_resource(self.org))
        self.assertEqual(self.state(message)["state"], "DELIVERED")
        with patch("chatballs.api_connector.outbound._send_command") as send_again:
            deliver_connector_command(event.payload, TenantContext.for_resource(self.org))
            send_again.assert_not_called()

    def test_cross_connection_command_does_not_match(self):
        message, _ = self.create_reply()
        second = create_integration(
            context=system_tenant_context(self.org),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR, name="Other receipt adapter",
                config={"connectorService": "custom_adapter"},
            ),
        )
        other_credential = self.client.post(
            f"/api/v1/integrations/{second.pk}/connector-credential/",
            data={}, format="json",
        ).data
        candidate = self.receipt(
            self.state(message)["commandId"], "DELIVERED",
        )
        candidate["source_id"] = other_credential["sourceId"]
        self.assertEqual(
            self.send(candidate, token=other_credential["token"], url=other_credential["webhookPath"]).status_code,
            409,
        )
        self.assertEqual(self.state(message)["state"], "QUEUED")
