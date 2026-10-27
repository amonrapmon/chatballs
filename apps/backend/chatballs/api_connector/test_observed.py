"""Provider-observed outgoing text must not masquerade as inbound or Chatballs send."""
from __future__ import annotations

from copy import deepcopy

from django.test import TestCase

from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    ExpectedResponder,
    Message,
    MessageAuthor,
)
from chatballs.events.models import InboxEvent, OutboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.testing import TenantAPIClient, system_tenant_context


class APIConnectorObservedOutgoingTests(TestCase):
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
                "occurred_at": "2026-10-23T12:03:00Z",
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

    def test_observed_reply_appears_in_native_history_without_new_outbox(self):
        conversation = self.open_conversation()
        before = OutboxEvent.objects.count()
        result = self.send(self.observed())
        self.assertEqual(result.status_code, 202, result.data)
        self.assertEqual(result.data, {"accepted": True, "id": "observed-1"})
        messages = list(Message.objects.filter(conversation=conversation).order_by("pk"))
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].author_type, MessageAuthor.CONTACT)
        reply = messages[1]
        self.assertEqual(reply.author_type, MessageAuthor.OPERATOR)
        self.assertIsNone(reply.author_user_id)
        self.assertEqual(reply.external_id, "native-operator-1")
        self.assertEqual(reply.connector_origin, "EXTERNAL_OBSERVED")
        self.assertEqual(OutboxEvent.objects.count(), before)
        history = self.client.get(f"/api/v1/conversations/{conversation.pk}/messages/")
        self.assertEqual(history.status_code, 200)
        found = next(m for m in history.data["items"] if m["id"] == reply.pk)
        self.assertEqual(found["connectorOrigin"], "EXTERNAL_OBSERVED")
        self.assertIsNone(found["authorUserId"])
        self.assertFalse(found.get("connectorDelivery"))

    def test_unmatched_open_chat_returns_retryable_conflict_without_consuming_id(self):
        event = self.observed()
        unknown = self.send(event)
        self.assertEqual(unknown.status_code, 409)
        self.assertEqual(unknown.data["error"], "unknown_conversation")
        self.assertFalse(InboxEvent.objects.filter(source__startswith="api_connector_observed").exists())
        self.open_conversation()
        self.assertEqual(self.send(event).status_code, 202)

    def test_replay_and_duplicate_provider_id_are_idempotent(self):
        conversation = self.open_conversation()
        event = self.observed()
        self.assertEqual(self.send(event).status_code, 202)
        self.assertEqual(self.send(event).status_code, 202)
        duplicate_new_event = deepcopy(event)
        duplicate_new_event["event"]["id"] = "observed-2"
        self.assertEqual(self.send(duplicate_new_event).status_code, 202)
        self.assertEqual(Message.objects.filter(conversation=conversation).count(), 2)
        self.assertEqual(
            InboxEvent.objects.filter(source=f"api_connector_observed:{self.integration.pk}").count(),
            2,
        )
        changed = deepcopy(event)
        changed["message"]["text"] = "Изменено"
        conflict = self.send(changed)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["error"], "external_message_id_conflict")

    def test_same_event_id_with_new_provider_identity_is_conflict(self):
        self.open_conversation()
        event = self.observed()
        self.assertEqual(self.send(event).status_code, 202)
        changed = deepcopy(event)
        changed["message"]["external_message_id"] = "native-operator-2"
        self.assertEqual(self.send(changed).status_code, 409)
        self.assertEqual(
            Message.objects.filter(connector_origin="EXTERNAL_OBSERVED").count(), 1,
        )

    def test_ai_conversation_pauses_without_claiming_a_staff_member(self):
        conversation = self.open_conversation()
        conversation.control_mode = ControlMode.AI
        conversation.expected_responder = ExpectedResponder.AI
        conversation.waiting_since = None
        conversation.save(update_fields=["control_mode", "expected_responder", "waiting_since"])
        outbox_before = OutboxEvent.objects.count()
        self.assertEqual(self.send(self.observed()).status_code, 202)
        conversation.refresh_from_db()
        self.assertEqual(conversation.control_mode, ControlMode.PAUSED)
        self.assertEqual(conversation.expected_responder, ExpectedResponder.OPERATOR)
        self.assertIsNotNone(conversation.waiting_since)
        self.assertIsNone(conversation.assigned_operator_id)
        self.assertEqual(OutboxEvent.objects.count(), outbox_before)

    def test_human_assignment_remains_and_customer_is_expected(self):
        conversation = self.open_conversation()
        conversation.control_mode = ControlMode.HUMAN
        conversation.assigned_operator = self.owner
        conversation.waiting_since = None
        conversation.save(update_fields=["control_mode", "assigned_operator", "waiting_since"])
        self.assertEqual(self.send(self.observed()).status_code, 202)
        conversation.refresh_from_db()
        self.assertEqual(conversation.control_mode, ControlMode.HUMAN)
        self.assertEqual(conversation.assigned_operator_id, self.owner.pk)
        self.assertEqual(conversation.expected_responder, ExpectedResponder.CUSTOMER)
        self.assertIsNone(Message.objects.get(connector_origin="EXTERNAL_OBSERVED").author_user_id)

    def test_wrong_route_and_connection_cannot_add_an_observed_message(self):
        self.open_conversation()
        observed = self.observed()
        self.assertEqual(self.send(observed, token="wrong-token").status_code, 401)
        wrong_source = deepcopy(observed)
        wrong_source["source_id"] = "connection-99999"
        self.assertEqual(self.send(wrong_source).status_code, 409)
        self.assertEqual(self.send(self.observed(chat_id="not-our-chat")).status_code, 409)
        second = create_integration(
            context=system_tenant_context(self.organization),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR, name="Other adapter",
                config={"connectorService": "custom_adapter"},
            ),
        )
        credential = self.client.post(
            f"/api/v1/integrations/{second.pk}/connector-credential/",
            data={}, format="json",
        ).data
        foreign = deepcopy(observed)
        foreign["source_id"] = credential["sourceId"]
        result = self.send(foreign, token=credential["token"], url=credential["webhookPath"])
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["error"], "unknown_conversation")
        self.assertFalse(Message.objects.filter(connector_origin="EXTERNAL_OBSERVED").exists())

    def test_contact_id_collision_cannot_overwrite_inbound(self):
        self.open_conversation()
        bad = self.send(self.observed(external_id="guest-message-1"))
        self.assertEqual(bad.status_code, 409)
        self.assertEqual(bad.data["error"], "external_message_id_conflict")
        self.assertFalse(Message.objects.filter(connector_origin="EXTERNAL_OBSERVED").exists())

    def test_malformed_and_unsupported_variants_fail_closed(self):
        self.open_conversation()
        good = self.observed()
        cases = [
            ({**good, "sender": {"external_user_id": "u", "author_user_id": 1}}, 400),
            ({**good, "message": {**good["message"], "actor": "contact"}}, 422),
            ({**good, "message": {**good["message"], "direction": "inbound"}}, 422),
            ({**good, "message": {**good["message"], "attachments": [{"x": 1}]}}, 422),
            ({**good, "message": {**good["message"], "html": "<b>hello</b>"}}, 422),
            ({**good, "message": {**good["message"], "kind": "file"}}, 422),
            ({**good, "message": {**good["message"], "text": ""}}, 400),
            ({**good, "conversation": {"external_chat_id": "chat-1", "thread": {"id": "1"}}}, 422),
        ]
        for payload, status in cases:
            with self.subTest(payload=payload):
                self.assertEqual(self.send(payload).status_code, status)
        self.assertFalse(Message.objects.filter(connector_origin="EXTERNAL_OBSERVED").exists())
