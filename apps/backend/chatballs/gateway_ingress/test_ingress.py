from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from chatballs.channels.models import Channel
from chatballs.conversations.models import Message, MessageAuthor, MessageKind
from chatballs.conversations.serializers import message_payload
from chatballs.events.models import InboxEvent
from chatballs.gateway_ingress.payloads import GatewayPayloadError, parse_inbound_payload
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider


def _gateway_payload() -> dict:
    return {
        "schema": "intercom-gw.chatballs.inbound.v1",
        "source_id": "tg-studio-main",
        "event_id": "gateway-event-1",
        "occurred_at": "2026-09-19T10:15:00Z",
        "chat": {"external_chat_id": "chat-1", "type": "personal"},
        "sender": {
            "external_user_id": "user-1",
            "display_name": "Анна",
            "username": "anna",
            "phone": None,
            "avatar_url": None,
        },
        "message": {
            "external_message_id": "provider-message-1",
            "reply_to_message_id": None,
            "text": "Здравствуйте",
        },
    }


class GatewayPayloadParsingTests(SimpleTestCase):
    def test_parser_preserves_text_and_maps_transport_metadata(self) -> None:
        payload = _gateway_payload()
        payload["message"]["text"] = "  hello  "
        payload["message"]["reply_to_message_id"] = "provider-message-0"

        parsed = parse_inbound_payload(payload)

        self.assertEqual(parsed.inbound.text, "  hello  ")
        self.assertEqual(
            parsed.inbound.external_occurred_at,
            datetime(2026, 9, 19, 10, 15, tzinfo=UTC),
        )
        self.assertEqual(parsed.inbound.external_reply_to_id, "provider-message-0")

    def test_parser_does_not_treat_sender_phone_as_contact_share(self) -> None:
        payload = _gateway_payload()
        payload["sender"]["phone"] = "79990000000"

        parsed = parse_inbound_payload(payload)

        self.assertEqual(parsed.inbound.phone, "")

    def test_parser_rejects_whitespace_only_text(self) -> None:
        payload = _gateway_payload()
        payload["message"]["text"] = "     "

        with self.assertRaises(GatewayPayloadError):
            parse_inbound_payload(payload)


class GatewayIngressTests(TestCase):
    endpoint_template = "/api/v1/gateway/integrations/{}/inbound/"

    def setUp(self) -> None:
        result = bootstrap_owner(email="gateway-ingress@example.com", password="Owner-Password-2026!")
        self.organization = result.organization
        self.owner = result.owner
        self.channel = Channel.objects.create(
            organization=self.organization,
            code="gateway-ingress",
            name="Gateway ingress",
        )
        self.integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.GATEWAY,
            name="Gateway ingress source",
            secret="gateway-secret",
            config={"source_id": "tg-studio-main", "base_url": "https://gateway.example.test/"},
            channel=self.channel,
        )
        self.client = APIClient()

    def _path(self, integration: Integration | None = None) -> str:
        return self.endpoint_template.format((integration or self.integration).id)

    def _payload(self) -> dict:
        return _gateway_payload()

    def _post(self, payload: dict | None = None, *, secret: str = "gateway-secret", integration=None):
        return self.client.post(
            self._path(integration),
            data=payload if payload is not None else self._payload(),
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {secret}",
        )

    def test_valid_inbound_text_creates_one_customer_message(self) -> None:
        response = self._post()

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"accepted": True})
        message = Message.objects.get(external_id="provider-message-1")
        self.assertEqual(message.text, "Здравствуйте")
        self.assertIsNone(message.gateway_command_id)
        self.assertIsNone(message.delivery_status or None)
        self.assertIsNone(message.delivery_status_at)
        self.assertIsNone(message.delivery_failure_kind or None)
        serialized = message_payload(message)
        self.assertIsNone(serialized["deliveryStatus"])
        self.assertIsNone(serialized["deliveryStatusAt"])
        self.assertIsNone(serialized["deliveryFailureKind"])
        self.assertEqual(
            message.external_occurred_at,
            datetime(2026, 9, 19, 10, 15, tzinfo=UTC),
        )
        self.assertEqual(message.external_reply_to_id, "")
        self.assertEqual(
            InboxEvent.objects.get(source=f"gateway:{self.integration.id}").external_event_id,
            "gateway-event-1",
        )

    def test_sender_phone_metadata_does_not_create_contact_share_ack(self) -> None:
        payload = self._payload()
        payload["sender"]["phone"] = "79990000000"

        response = self._post(payload)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(Message.objects.count(), 1)
        message = Message.objects.get(external_id="provider-message-1")
        self.assertEqual(message.author_type, MessageAuthor.CONTACT)
        self.assertEqual(message.kind, MessageKind.TEXT)
        self.assertEqual(message.text, "Здравствуйте")
        self.assertFalse(Message.objects.filter(author_type=MessageAuthor.AI).exists())

    def test_inbound_preserves_transport_metadata_and_receipt_timestamp(self) -> None:
        payload = self._payload()
        payload["event_id"] = "gateway-event-with-reply"
        payload["occurred_at"] = "2020-01-01T00:00:00Z"
        payload["message"]["external_message_id"] = "provider-message-with-reply"
        payload["message"]["reply_to_message_id"] = "provider-message-0"
        payload["message"]["text"] = "  hello  "

        response = self._post(payload)

        self.assertEqual(response.status_code, 202)
        message = Message.objects.get(external_id="provider-message-with-reply")
        self.assertEqual(message.text, "  hello  ")
        self.assertEqual(message.external_reply_to_id, "provider-message-0")
        self.assertEqual(
            message.external_occurred_at,
            datetime(2020, 1, 1, tzinfo=UTC),
        )
        self.assertGreater(message.created_at, message.external_occurred_at)

    def test_whitespace_only_text_is_rejected(self) -> None:
        payload = self._payload()
        payload["message"]["text"] = "     "

        response = self._post(payload)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Message.objects.count(), 0)

    def test_duplicate_event_is_successful_without_second_message(self) -> None:
        first = self._post()
        duplicate_payload = self._payload()
        duplicate_payload["message"]["external_message_id"] = "provider-message-retry"
        second = self._post(duplicate_payload)

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(Message.objects.filter(external_id="provider-message-1").count(), 1)
        self.assertEqual(
            InboxEvent.objects.filter(
                source=f"gateway:{self.integration.id}",
                external_event_id="gateway-event-1",
            ).count(),
            1,
        )

    def test_invalid_secret_is_rejected(self) -> None:
        response = self._post(secret="wrong-secret")

        self.assertEqual(response.status_code, 401)

    def test_missing_secret_is_rejected(self) -> None:
        response = self.client.post(self._path(), data=self._payload(), format="json")

        self.assertEqual(response.status_code, 401)

    def test_wrong_source_id_is_rejected(self) -> None:
        payload = self._payload()
        payload["source_id"] = "another-source"

        response = self._post(payload)

        self.assertEqual(response.status_code, 409)

    def test_unknown_integration_is_rejected(self) -> None:
        response = self._post(integration=Integration(id=999999))

        self.assertEqual(response.status_code, 404)

    def test_non_gateway_integration_is_rejected(self) -> None:
        integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.TELEGRAM,
            name="Not a gateway",
            secret="telegram-secret",
            channel=self.channel,
        )

        response = self._post(secret="telegram-secret", integration=integration)

        self.assertEqual(response.status_code, 404)

    def test_inactive_integration_is_rejected(self) -> None:
        self.integration.is_active = False
        self.integration.save(update_fields=["is_active"])

        response = self._post()

        self.assertEqual(response.status_code, 409)

    def test_inactive_channel_is_rejected(self) -> None:
        self.channel.is_active = False
        self.channel.save(update_fields=["is_active"])

        response = self._post()

        self.assertEqual(response.status_code, 409)

    def test_group_chat_is_rejected(self) -> None:
        payload = self._payload()
        payload["chat"]["type"] = "group"

        response = self._post(payload)

        self.assertEqual(response.status_code, 422)

    def test_malformed_schema_is_rejected(self) -> None:
        payload = deepcopy(self._payload())
        del payload["message"]["external_message_id"]

        response = self._post(payload)

        self.assertEqual(response.status_code, 400)

    def test_human_organization_api_still_requires_human_session(self) -> None:
        path = f"/api/v1/organizations/{self.organization.public_id}/integrations/"

        anonymous = APIClient().get(path)
        self.assertEqual(anonymous.status_code, 404)

        self.assertTrue(self.client.login(email=self.owner.email, password="Owner-Password-2026!"))
        human = self.client.get(path)
        self.assertEqual(human.status_code, 200)
