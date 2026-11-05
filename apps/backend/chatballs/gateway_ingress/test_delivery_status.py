from datetime import UTC, datetime, timedelta
from unittest import mock
from uuid import uuid4

from django.test import TestCase
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
from chatballs.conversations.serializers import message_payload
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider


class GatewayDeliveryStatusTests(TestCase):
    endpoint_template = "/api/v1/gateway/integrations/{}/delivery-status/"

    def setUp(self) -> None:
        bootstrap_owner(email="delivery-status@example.com", password="temporary-password")
        self.organization = self._organization()
        self.channel = Channel.objects.create(
            organization=self.organization,
            code="delivery-status",
            name="Delivery status",
        )
        self.integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.GATEWAY,
            name="Gateway delivery status",
            secret="gateway-secret",
            config={
                "source_id": "tg-studio-main",
                "base_url": "https://gateway.example.test/",
            },
            channel=self.channel,
        )
        self.contact = self.organization.contacts.create(name="Анна")
        self.conversation = Conversation.objects.create(
            organization=self.organization,
            channel=self.channel,
            connection=self.integration,
            contact=self.contact,
            external_chat_id="chat-1",
            control_mode=ControlMode.HUMAN,
            expected_responder=ExpectedResponder.OPERATOR,
        )
        self.client = APIClient()

    def _organization(self):
        from chatballs.identity.models import Organization

        return Organization.objects.get(slug="demo")

    def _message(self, *, status: str = "queued", external_id: str = "") -> Message:
        return Message.objects.create(
            conversation=self.conversation,
            author_type=MessageAuthor.OPERATOR,
            text="Ответ оператора",
            gateway_command_id=uuid4(),
            delivery_status=status,
            external_id=external_id,
        )

    def _payload(self, message: Message, **overrides: object) -> dict:
        payload = {
            "schema": "intercom-gw.chatballs.delivery-status.v1",
            "source_id": "tg-studio-main",
            "command_id": str(message.gateway_command_id),
            "external_chat_id": self.conversation.external_chat_id,
            "external_message_id": "provider-message-1",
            "status": "provider_accepted",
            "occurred_at": "2026-09-20T12:34:56Z",
            "failure_kind": None,
        }
        payload.update(overrides)
        return payload

    def _post(
        self,
        payload: dict,
        *,
        secret: str = "gateway-secret",
        integration: Integration | None = None,
    ):
        return self.client.post(
            self.endpoint_template.format((integration or self.integration).id),
            data=payload,
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {secret}" if secret else None,
        )

    def test_provider_accepted_binds_provider_id_and_returns_202(self) -> None:
        message = self._message()

        response = self._post(self._payload(message))

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"accepted": True})
        message.refresh_from_db()
        self.assertEqual(message.external_id, "provider-message-1")
        self.assertEqual(message.delivery_status, "provider_accepted")
        self.assertEqual(
            message.delivery_status_at,
            datetime(2026, 9, 20, 12, 34, 56, tzinfo=UTC),
        )
        self.assertEqual(message.delivery_failure_kind, "")
        serialized = message_payload(message)
        self.assertEqual(serialized["deliveryStatus"], "provider_accepted")
        self.assertEqual(
            serialized["deliveryStatusAt"],
            "2026-09-20T12:34:56+00:00",
        )
        self.assertIsNone(serialized["deliveryFailureKind"])

    def test_missing_or_wrong_bearer_is_401(self) -> None:
        message = self._message()
        payload = self._payload(message)

        missing = self.client.post(
            self.endpoint_template.format(self.integration.id), data=payload, format="json"
        )
        wrong = self._post(payload, secret="wrong-secret")

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(wrong.status_code, 401)

    def test_wrong_source_is_409_without_mutation(self) -> None:
        message = self._message()
        before = (message.external_id, message.delivery_status, message.delivery_status_at)

        response = self._post(self._payload(message, source_id="other-source"))

        self.assertEqual(response.status_code, 409)
        message.refresh_from_db()
        self.assertEqual(
            (message.external_id, message.delivery_status, message.delivery_status_at),
            before,
        )

    def test_unknown_command_is_404(self) -> None:
        response = self._post(
            {
                "schema": "intercom-gw.chatballs.delivery-status.v1",
                "source_id": "tg-studio-main",
                "command_id": str(uuid4()),
                "external_chat_id": "chat-1",
                "external_message_id": "provider-message-1",
                "status": "delivered",
            }
        )

        self.assertEqual(response.status_code, 404)

    def test_unsupported_status_is_422_without_mutation(self) -> None:
        message = self._message()

        response = self._post(self._payload(message, status="queued"))

        self.assertEqual(response.status_code, 422)
        message.refresh_from_db()
        self.assertEqual(message.delivery_status, "queued")
        self.assertEqual(message.external_id, "")

    def test_malformed_status_payload_is_400_without_mutation(self) -> None:
        message = self._message()

        response = self._post(self._payload(message, status="delivered", external_message_id=None))

        self.assertEqual(response.status_code, 400)
        message.refresh_from_db()
        self.assertEqual(message.delivery_status, "queued")
        self.assertEqual(message.external_id, "")

    def test_command_is_scoped_to_authenticated_integration(self) -> None:
        other_integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.GATEWAY,
            name="Other gateway source",
            secret="other-gateway-secret",
            config={"source_id": "tg-studio-main"},
            channel=self.channel,
        )
        message = self._message()

        response = self._post(
            self._payload(message),
            secret="other-gateway-secret",
            integration=other_integration,
        )

        self.assertEqual(response.status_code, 404)
        message.refresh_from_db()
        self.assertEqual(message.delivery_status, "queued")
        self.assertEqual(message.external_id, "")

    def test_chat_mismatch_is_409_without_mutation(self) -> None:
        message = self._message()

        response = self._post(self._payload(message, external_chat_id="other-chat"))

        self.assertEqual(response.status_code, 409)
        message.refresh_from_db()
        self.assertEqual(message.external_id, "")
        self.assertEqual(message.delivery_status, "queued")

    def test_provider_id_conflict_is_409_without_mutation(self) -> None:
        message = self._message(external_id="provider-original")
        before = (message.external_id, message.delivery_status, message.delivery_status_at)

        response = self._post(
            self._payload(
                message,
                external_message_id="provider-different",
                status="delivered",
            )
        )

        self.assertEqual(response.status_code, 409)
        message.refresh_from_db()
        self.assertEqual(
            (message.external_id, message.delivery_status, message.delivery_status_at),
            before,
        )

    def test_same_provider_id_and_status_is_idempotent(self) -> None:
        message = self._message()
        first = self._post(self._payload(message))
        message.refresh_from_db()
        first_timestamp = message.delivery_status_at

        with mock.patch(
            "chatballs.gateway_ingress.delivery_status.timezone.now",
            return_value=timezone.now() + timedelta(hours=1),
        ):
            duplicate = self._post(self._payload(message))

        message.refresh_from_db()
        self.assertEqual(first.status_code, 202)
        self.assertEqual(duplicate.status_code, 202)
        self.assertEqual(message.delivery_status_at, first_timestamp)
