"""End-to-end HTTP ingress boundary without any Green API dependency."""
from __future__ import annotations

import json
from copy import deepcopy

from django.test import TestCase
from django.urls import reverse

from chatballs.conversations.models import (
    ConnectionIdentity, Conversation, ControlMode, Message, MessageAuthor,
)
from chatballs.events.models import InboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import Organization
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.testing import TenantAPIClient, system_tenant_context


class APIConnectorIngressTests(TestCase):
    def setUp(self):
        result = bootstrap_owner(
            email="connector-ingress-owner@example.com", password="Temporary-Password-2026!",
        )
        self.org = result.organization
        self.owner = result.owner
        self.client = TenantAPIClient()
        self.client.force_login(self.owner)
        self.integration = create_integration(
            context=system_tenant_context(self.org),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR, name="External service",
                config={"connectorService": "custom_adapter"},
            ),
        )
        self.event_url = reverse("api-connector-events", kwargs={
            "organization_public_id": self.org.public_id,
            "integration_id": self.integration.id,
        })
        response = self.client.post(
            f"/api/v1/integrations/{self.integration.id}/connector-credential/",
            data={}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.token = response.data["token"]
        self.source = response.data["sourceId"]
        self.assertEqual(self.source, f"connection-{self.integration.id}")
        self.assertEqual(response.data["webhookPath"], self.event_url)

    def event(self, *, event_id="evt-1", message_id="provider-10", text="Здравствуйте"):
        return {
            "schema": "chatballs.api-connector.event.v1",
            "source_id": self.source,
            "event": {
                "id": event_id, "type": "message.created",
                "occurred_at": "2026-10-23T12:00:00Z",
            },
            "conversation": {"external_chat_id": "external-chat-1", "thread": None},
            "sender": {
                "external_user_id": "client-1", "display_name": "Test guest",
                "username": None, "avatar_ref": None,
            },
            "message": {
                "external_message_id": message_id, "direction": "inbound",
                "origin": "external_observed", "actor": "contact",
                "kind": "text", "text": text, "attachments": [],
                "reply_to_external_message_id": None, "contact_share": None,
                "html": None,
            },
        }

    def send(self, payload, token=None):
        return self.client.post(
            self.event_url, payload, format="json",
            HTTP_AUTHORIZATION=f"Bearer {self.token if token is None else token}",
        )

    def test_text_arrives_in_operator_inbox_and_duplicate_replay_is_safe(self):
        payload = self.event()
        first = self.send(payload)
        self.assertEqual(first.status_code, 202, first.data)
        second = self.send(payload)
        self.assertEqual(second.status_code, 202, second.data)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(InboxEvent.objects.count(), 1)
        conversation = Conversation.objects.get()
        self.assertEqual(conversation.control_mode, ControlMode.PAUSED)
        self.assertEqual(conversation.connection_id, self.integration.id)
        self.assertEqual(conversation.route_external_user_id, "client-1")
        self.assertEqual(conversation.external_chat_id, "external-chat-1")
        self.assertEqual(Message.objects.get().author_type, MessageAuthor.CONTACT)
        self.assertEqual(Message.objects.get().external_id, "provider-10")
        self.assertEqual(ConnectionIdentity.objects.get().external_user_id, "client-1")

    def test_duplicate_event_with_changed_text_conflicts(self):
        first = self.send(self.event())
        self.assertEqual(first.status_code, 202, first.data)
        changed = self.send(self.event(text="Изменённый текст"))
        self.assertEqual(changed.status_code, 409, changed.data)
        self.assertEqual(changed.data["error"], "id_conflict")
        self.assertEqual(Message.objects.count(), 1)

    def test_duplicate_event_with_changed_message_id_conflicts(self):
        self.assertEqual(self.send(self.event()).status_code, 202)
        bad = self.send(self.event(message_id="provider-11"))
        self.assertEqual(bad.status_code, 409)
        self.assertEqual(Message.objects.count(), 1)

    def test_source_secret_and_scope_are_enforced(self):
        self.assertEqual(self.send(self.event(), token="not-valid").status_code, 401)
        different_source = self.event()
        different_source["source_id"] = "connection-99999"
        self.assertEqual(self.send(different_source).status_code, 409)
        self.integration.is_active = False
        self.integration.save(update_fields=["is_active"])
        self.assertEqual(self.send(self.event()).status_code, 403)
        self.assertEqual(Message.objects.count(), 0)

    def test_token_rotation_immediately_revokes_previous_token(self):
        old = self.token
        response = self.client.post(
            f"/api/v1/integrations/{self.integration.id}/connector-credential/",
            data={}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        new = response.data["token"]
        self.assertNotEqual(old, new)
        self.assertEqual(self.send(self.event(), token=old).status_code, 401)
        self.assertEqual(self.send(self.event(), token=new).status_code, 202)
        self.assertNotIn(new, str(response.data["integration"]))

    def test_no_cross_tenant_access_even_with_valid_token(self):
        other = Organization.objects.create(name="Another", slug="another-connector-test")
        path = reverse("api-connector-events", kwargs={
            "organization_public_id": other.public_id,
            "integration_id": self.integration.id,
        })
        reply = self.client.post(
            path, self.event(), format="json", HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(reply.status_code, 404)
        self.assertEqual(Message.objects.count(), 0)

    def test_unsupported_events_media_and_unsafe_fields_fail_closed(self):
        event = self.event()
        cases = []
        media = deepcopy(event)
        media["message"]["kind"] = "file"
        media["message"]["attachments"] = [{"media_ref": "fake"}]
        cases.append((media, 422))
        outgoing = deepcopy(event)
        outgoing["event"]["type"] = "message.observed_outgoing"
        cases.append((outgoing, 422))
        token_leak = deepcopy(event)
        token_leak["apiTokenInstance"] = "should-never-persist"
        cases.append((token_leak, 400))
        source_html = deepcopy(event)
        source_html["message"]["html"] = "<script>bad</script>"
        cases.append((source_html, 422))
        for payload, expected in cases:
            with self.subTest(payload=payload):
                reply = self.send(payload)
                self.assertEqual(reply.status_code, expected, reply.data)
        self.assertEqual(Message.objects.count(), 0)

    def test_outbound_operator_reply_is_rejected_until_transport_exists(self):
        self.assertEqual(self.send(self.event()).status_code, 202)
        conversation = Conversation.objects.get()
        response = self.client.post(
            f"/api/v1/conversations/{conversation.id}/messages/",
            data={"text": "Ответ оператора"}, format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Message.objects.count(), 1)

    def test_duplicate_json_keys_and_nonfinite_rejected(self):
        body = b'{"schema":"a","schema":"b"}'
        r = self.client.generic(
            "POST", self.event_url, body, content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(r.status_code, 400)
        sample = json.dumps(self.event()).replace('"Здравствуйте"', 'NaN')
        r = self.client.generic(
            "POST", self.event_url, sample.encode(), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(r.status_code, 400)

    def test_content_type_and_size_guard(self):
        r = self.client.generic(
            "POST", self.event_url, b"hello", content_type="text/plain",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(r.status_code, 400)
        r = self.client.generic(
            "POST", self.event_url, b" " * 65537,
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        self.assertEqual(r.status_code, 413)
