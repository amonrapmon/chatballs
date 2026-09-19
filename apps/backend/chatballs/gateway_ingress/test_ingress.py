from __future__ import annotations

from copy import deepcopy

from django.test import TestCase
from rest_framework.test import APIClient

from chatballs.channels.models import Channel
from chatballs.conversations.models import Message
from chatballs.events.models import InboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider


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
        self.assertEqual(
            InboxEvent.objects.get(source=f"gateway:{self.integration.id}").external_event_id,
            "gateway-event-1",
        )

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
