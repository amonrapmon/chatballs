from __future__ import annotations

from datetime import UTC, datetime
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from chatballs.channels.models import Channel
from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    ExpectedResponder,
    Message,
    MessageAuthor,
)
from chatballs.events.models import EventOwnership, InboxEvent, OutboxEvent
from chatballs.gateway_ingress.payloads import GatewayPayloadError, parse_operator_mirror_payload
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import EmployeeRole, HumanUser, OrganizationMembership
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider


def _payload(**overrides: object) -> dict:
    payload = {
        "schema": "intercom-gw.chatballs.operator-mirror.v1",
        "source_id": "tg-studio-main",
        "event_id": "outgoingMessageReceived:chat-1:provider-message-1",
        "occurred_at": "2026-09-20T12:34:56Z",
        "chat": {"external_chat_id": "chat-1", "type": "personal"},
        "operator": {"external_user_id": "provider-account", "display_name": "Operator"},
        "message": {
            "external_message_id": "provider-message-1",
            "reply_to_message_id": "provider-message-0",
            "text": "Нативный ответ",
        },
    }
    payload.update(overrides)
    return payload


class GatewayOperatorMirrorPayloadTests(SimpleTestCase):
    def test_parser_preserves_native_message_metadata(self) -> None:
        parsed = parse_operator_mirror_payload(_payload())

        self.assertEqual(parsed.source_id, "tg-studio-main")
        self.assertEqual(parsed.event_id, "outgoingMessageReceived:chat-1:provider-message-1")
        self.assertEqual(parsed.external_chat_id, "chat-1")
        self.assertEqual(parsed.external_user_id, "provider-account")
        self.assertEqual(parsed.display_name, "Operator")
        self.assertEqual(parsed.external_message_id, "provider-message-1")
        self.assertEqual(parsed.reply_to_message_id, "provider-message-0")
        self.assertEqual(parsed.text, "Нативный ответ")
        self.assertEqual(parsed.occurred_at, datetime(2026, 9, 20, 12, 34, 56, tzinfo=UTC))

    def test_parser_rejects_non_personal_chat_and_empty_text(self) -> None:
        payload = _payload()
        payload["chat"] = {"external_chat_id": "group-1", "type": "group"}
        with self.assertRaises(GatewayPayloadError):
            parse_operator_mirror_payload(payload)

        payload = _payload()
        payload["message"] = {**payload["message"], "text": "   "}
        with self.assertRaises(GatewayPayloadError):
            parse_operator_mirror_payload(payload)


class GatewayOperatorMirrorTests(TestCase):
    endpoint_template = "/api/v1/gateway/integrations/{}/operator-mirror/"

    def setUp(self) -> None:
        result = bootstrap_owner(email="operator-mirror@example.com", password="temporary-password")
        self.organization = result.organization
        self.owner = result.owner
        self.channel = Channel.objects.create(
            organization=self.organization,
            code="operator-mirror",
            name="Operator mirror",
        )
        self.native_user = HumanUser.objects.create_user(
            email="tg-native@example.com",
            password=None,
            full_name="TG Native",
            is_active=False,
        )
        OrganizationMembership.objects.create(
            organization=self.organization,
            user=self.native_user,
            role=EmployeeRole.EMPLOYEE,
            position_title="TG Native",
        )
        self.integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.GATEWAY,
            name="TG Gateway",
            secret="gateway-secret",
            config={
                "source_id": "tg-studio-main",
                "base_url": "https://gateway.example.test/",
                "native_operator_user_id": self.native_user.id,
            },
            channel=self.channel,
        )
        self.contact = self.organization.contacts.create(name="Client")
        self.conversation = Conversation.objects.create(
            organization=self.organization,
            channel=self.channel,
            connection=self.integration,
            contact=self.contact,
            external_chat_id="chat-1",
            control_mode=ControlMode.AI,
            expected_responder=ExpectedResponder.AI,
            waiting_since=timezone.now(),
            assigned_operator=self.owner,
        )
        self.client = APIClient()

    def _post(self, payload: dict | None = None, *, secret: str = "gateway-secret"):
        return self.client.post(
            self.endpoint_template.format(self.integration.id),
            data=payload if payload is not None else _payload(),
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {secret}" if secret else None,
        )

    def test_native_reply_creates_operator_message_without_outbound_or_ai_work(self) -> None:
        outbox_before = OutboxEvent.objects.count()
        with (
            mock.patch("chatballs.conversations.transports.send_reply") as send_reply,
            mock.patch("chatballs.conversations.ai_turn.request_ai_turn") as request_ai_turn,
        ):
            response = self._post()

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"accepted": True})
        self.assertEqual(Message.objects.filter(conversation=self.conversation).count(), 1)
        message = Message.objects.get(conversation=self.conversation)
        self.assertEqual(message.author_type, MessageAuthor.OPERATOR)
        self.assertEqual(message.author_user_id, self.native_user.id)
        self.assertEqual(message.text, "Нативный ответ")
        self.assertEqual(message.external_id, "provider-message-1")
        self.assertEqual(message.external_reply_to_id, "provider-message-0")
        self.assertEqual(
            message.external_occurred_at,
            datetime(2026, 9, 20, 12, 34, 56, tzinfo=UTC),
        )
        self.assertIsNone(message.gateway_command_id)
        self.assertEqual(message.ai_turn_state, "NONE")
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, ControlMode.HUMAN)
        self.assertEqual(self.conversation.expected_responder, ExpectedResponder.CUSTOMER)
        self.assertIsNone(self.conversation.waiting_since)
        self.assertEqual(self.conversation.assigned_operator_id, self.owner.id)
        self.assertEqual(InboxEvent.objects.count(), 1)
        event = InboxEvent.objects.get()
        self.assertEqual(event.source, f"gateway-operator:{self.integration.id}")
        self.assertEqual(event.external_event_id, _payload()["event_id"])
        self.assertEqual(event.ownership, EventOwnership.TENANT)
        self.assertEqual(event.organization_id, self.organization.id)
        self.assertEqual(OutboxEvent.objects.count(), outbox_before)
        send_reply.assert_not_called()
        request_ai_turn.assert_not_called()

    def test_duplicate_provider_event_does_not_create_a_second_message(self) -> None:
        first = self._post()
        second = self._post()

        self.assertEqual((first.status_code, second.status_code), (202, 202))
        self.assertEqual(Message.objects.filter(conversation=self.conversation).count(), 1)
        self.assertEqual(InboxEvent.objects.count(), 1)

    def test_missing_conversation_is_recorded_without_creating_contact_or_dialog(self) -> None:
        self.conversation.delete()
        contacts_before = self.organization.contacts.count()
        payload = _payload(event_id="event-no-conversation")

        response = self._post(payload)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(self.organization.contacts.count(), contacts_before)
        self.assertFalse(Conversation.objects.filter(connection=self.integration).exists())
        self.assertEqual(InboxEvent.objects.filter(external_event_id="event-no-conversation").count(), 1)

    def test_invalid_credentials_or_source_do_not_create_events(self) -> None:
        unauthorized = self._post(secret="wrong")
        wrong_source = self._post(_payload(source_id="another-source"))

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(wrong_source.status_code, 409)
        self.assertFalse(InboxEvent.objects.exists())
        self.assertFalse(Message.objects.exists())

    def test_native_user_without_organization_membership_is_rejected(self) -> None:
        OrganizationMembership.objects.filter(user=self.native_user).delete()

        response = self._post()

        self.assertEqual(response.status_code, 409)
        self.assertFalse(InboxEvent.objects.exists())
        self.assertFalse(Message.objects.exists())
