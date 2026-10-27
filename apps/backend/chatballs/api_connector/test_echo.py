"""Native Connector own-send echo: correlation only, never a second message/send."""
from __future__ import annotations

from copy import deepcopy

from django.test import TestCase

from chatballs.api_connector.outbound import CONNECTOR_OUTBOUND_REQUESTED
from chatballs.conversations.models import Conversation, Message
from chatballs.events.models import InboxEvent, OutboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.testing import TenantAPIClient, system_tenant_context


class APIConnectorEchoTests(TestCase):
    def setUp(self):
        result = bootstrap_owner(
            email="connector-echo-owner@example.com",
            password="Temporary-Password-2026!",
        )
        self.organization, self.owner = result.organization, result.owner
        self.client = TenantAPIClient()
        self.client.force_login(self.owner)
        self.integration = create_integration(
            context=system_tenant_context(self.organization),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR,
                name="Echo adapter", config={"connectorService": "custom_adapter"},
            ),
        )
        credential = self.client.post(
            f"/api/v1/integrations/{self.integration.pk}/connector-credential/",
            data={}, format="json",
        )
        self.assertEqual(credential.status_code, 201)
        self.token = credential.data["token"]
        self.webhook = credential.data["webhookPath"]
        self.source = credential.data["sourceId"]

    def send(self, payload, *, token=None, url=None):
        return self.client.post(
            url or self.webhook, payload, format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token if token is None else token}",
        )

    def reply(self, text="Reply"):
        configured = self.client.post(
            f"/api/v1/integrations/{self.integration.pk}/connector-transport/",
            data={
                "url": "http://127.0.0.1:9081/v1/commands",
                "token": "echo-adapter-command-token-1234",
            }, format="json",
        )
        self.assertEqual(configured.status_code, 200)
        incoming = {
            "schema": "chatballs.api-connector.event.v1",
            "source_id": self.source,
            "event": {
                "id": "echo-inbound-1", "type": "message.created",
                "occurred_at": "2026-10-23T12:00:00Z",
            },
            "conversation": {"external_chat_id": "chat-1"},
            "sender": {"external_user_id": "user-1", "display_name": "Guest"},
            "message": {
                "external_message_id": "incoming-1",
                "direction": "inbound", "origin": "external_observed",
                "actor": "contact", "kind": "text", "text": "Hello",
                "attachments": [],
            },
        }
        self.assertEqual(self.send(incoming).status_code, 202)
        conversation = Conversation.objects.get()
        response = self.client.post(
            f"/api/v1/conversations/{conversation.pk}/messages/",
            data={"text": text}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        message = Message.objects.get(pk=response.data["message"]["id"])
        self.assertEqual(message.connector_delivery["state"], "QUEUED")
        return message

    def echo(self, *, event_id="echo-1", command_id=None,
             provider_id="provider-1", chat_id="chat-1"):
        echo = {"origin": "command_echo"}
        if command_id is not None:
            echo["command_id"] = command_id
        if provider_id is not None:
            echo["external_message_id"] = provider_id
        return {
            "schema": "chatballs.api-connector.event.v1",
            "source_id": self.source,
            "event": {
                "id": event_id, "type": "message.echo",
                "occurred_at": "2026-10-23T12:02:00Z",
            },
            "conversation": {"external_chat_id": chat_id},
            "echo": echo,
        }

    def test_command_echo_correlates_without_new_message_or_outbox(self):
        reply = self.reply()
        count = Message.objects.count()
        commands = OutboxEvent.objects.filter(
            event_type=CONNECTOR_OUTBOUND_REQUESTED,
        ).count()
        candidate = self.echo(command_id=reply.connector_delivery["commandId"])
        result = self.send(candidate)
        self.assertEqual(result.status_code, 202, result.data)
        self.assertEqual(result.data, {"accepted": True, "id": "echo-1"})
        reply.refresh_from_db()
        self.assertEqual(reply.connector_delivery["state"], "QUEUED")
        self.assertEqual(reply.connector_delivery["providerMessageId"], "provider-1")
        self.assertIn("echoObservedAt", reply.connector_delivery)
        self.assertEqual(Message.objects.count(), count)
        self.assertEqual(
            OutboxEvent.objects.filter(event_type=CONNECTOR_OUTBOUND_REQUESTED).count(),
            commands,
        )
        self.assertEqual(
            InboxEvent.objects.filter(source=f"api_connector_echo:{self.integration.pk}").count(),
            1,
        )

    def test_exact_replay_safe_changed_event_id_payload_conflicts(self):
        reply = self.reply()
        candidate = self.echo(command_id=reply.connector_delivery["commandId"])
        self.assertEqual(self.send(candidate).status_code, 202)
        self.assertEqual(self.send(candidate).status_code, 202)
        changed = deepcopy(candidate)
        changed["event"]["occurred_at"] = "2026-10-23T12:02:01Z"
        conflict = self.send(changed)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["error"], "id_conflict")
        self.assertEqual(
            InboxEvent.objects.filter(source=f"api_connector_echo:{self.integration.pk}").count(),
            1,
        )

    def test_provider_id_only_echo_requires_existing_receipt_correlation(self):
        reply = self.reply()
        echo = self.echo(command_id=None)
        self.assertEqual(self.send(echo).status_code, 409)
        self.assertEqual(
            InboxEvent.objects.filter(source=f"api_connector_echo:{self.integration.pk}").count(),
            0,
        )
        receipt = {
            "schema": "chatballs.api-connector.receipt.v1",
            "source_id": self.source,
            "event": {"id": "receipt-echo-1", "occurred_at": "2026-10-23T12:01:00Z"},
            "command_id": reply.connector_delivery["commandId"],
            "status": "PROVIDER_SENT", "provider_message_id": "provider-1",
        }
        self.assertEqual(self.send(receipt).status_code, 202)
        self.assertEqual(self.send(echo).status_code, 202)
        reply.refresh_from_db()
        self.assertEqual(reply.connector_delivery["state"], "PROVIDER_SENT")

    def test_echo_wrong_scope_chat_and_unknown_command_are_rejected(self):
        reply = self.reply()
        candidate = self.echo(command_id=reply.connector_delivery["commandId"])
        self.assertEqual(self.send(candidate, token="bad").status_code, 401)
        wrong_source = deepcopy(candidate)
        wrong_source["source_id"] = "connection-99999"
        self.assertEqual(self.send(wrong_source).status_code, 409)
        self.assertEqual(self.send(self.echo(
            command_id=reply.connector_delivery["commandId"], chat_id="other",
        )).status_code, 409)
        self.assertEqual(self.send(self.echo(
            command_id="11111111-1111-4111-8111-111111111111",
        )).status_code, 409)
        self.assertEqual(
            InboxEvent.objects.filter(source=f"api_connector_echo:{self.integration.pk}").count(),
            0,
        )

    def test_echo_does_not_allow_cross_integration_correlation(self):
        reply = self.reply()
        other = create_integration(
            context=system_tenant_context(self.organization),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR,
                name="Second echo adapter", config={"connectorService": "custom_adapter"},
            ),
        )
        credential = self.client.post(
            f"/api/v1/integrations/{other.pk}/connector-credential/",
            data={}, format="json",
        ).data
        event = self.echo(command_id=reply.connector_delivery["commandId"])
        event["source_id"] = credential["sourceId"]
        response = self.send(
            event, token=credential["token"], url=credential["webhookPath"],
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"], "unknown_command")

    def test_conflicting_provider_id_does_not_modify_message(self):
        reply = self.reply()
        command = reply.connector_delivery["commandId"]
        self.assertEqual(self.send(self.echo(command_id=command)).status_code, 202)
        other = self.send(self.echo(
            command_id=command, provider_id="different", event_id="echo-2",
        ))
        self.assertEqual(other.status_code, 409)
        self.assertEqual(other.data["error"], "echo_conflict")
        reply.refresh_from_db()
        self.assertEqual(reply.connector_delivery["providerMessageId"], "provider-1")
        self.assertEqual(
            InboxEvent.objects.filter(source=f"api_connector_echo:{self.integration.pk}").count(),
            1,
        )

    def test_malformed_echo_fails_closed(self):
        reply = self.reply()
        command_id = reply.connector_delivery["commandId"]
        cases = [
            ({**self.echo(command_id=command_id), "message": {"kind": "text"}}, 400),
            ({**self.echo(command_id=command_id), "sender": {"external_user_id": "x"}}, 400),
            ({**self.echo(command_id=command_id), "echo": {"origin": "command_echo"}}, 400),
            (self.echo(command_id="not-a-uuid"), 400),
            ({**self.echo(command_id=command_id), "echo": {
                "command_id": command_id, "origin": "external_observed",
            }}, 422),
        ]
        for payload, status in cases:
            with self.subTest(payload=payload):
                self.assertEqual(self.send(payload).status_code, status)
        self.assertEqual(
            InboxEvent.objects.filter(source=f"api_connector_echo:{self.integration.pk}").count(),
            0,
        )
