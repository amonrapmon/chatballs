from __future__ import annotations

import uuid
from unittest import mock

from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.gateway_delivery import (
    GATEWAY_DELIVERY_COMMAND_REQUESTED,
    GatewayDeliveryError,
)
from chatballs.conversations.models import (
    ConnectionIdentity,
    ControlMode,
    Conversation,
    ExpectedResponder,
    Message,
    MessageAuthor,
)
from chatballs.conversations.services import post_operator_message
from chatballs.events.models import EventOwnership, OutboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import HumanUser, Organization
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient as APIClient, tenant_context_for


class GatewayOperatorReplyTests(TestCase):
    def setUp(self) -> None:
        bootstrap_owner(email="owner@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.owner = HumanUser.objects.get(email="owner@example.com")
        self.channel = Channel.objects.create(
            organization=self.organization,
            code="gateway-replies",
            name="Gateway replies",
        )
        self.integration = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.GATEWAY,
            name="Gateway source",
            secret="gateway-secret",
            config={
                "source_id": "tg-studio-main",
                "base_url": "https://gateway.example.test/",
            },
            channel=self.channel,
        )
        self.contact = self.integration.organization.contacts.create(name="Анна")
        self.identity = ConnectionIdentity.objects.create(
            contact=self.contact,
            connection=self.integration,
            external_user_id="user-1",
            display_name="Анна",
        )
        self.conversation = Conversation.objects.create(
            organization=self.organization,
            channel=self.channel,
            connection=self.integration,
            contact=self.contact,
            external_chat_id="chat-1",
            control_mode=ControlMode.HUMAN,
            expected_responder=ExpectedResponder.OPERATOR,
            assigned_operator=self.owner,
        )
        self.context = tenant_context_for(self.owner, self.organization)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def test_gateway_operator_reply_commits_message_and_tenant_outbox_command(self) -> None:
        with mock.patch("chatballs.conversations.services.transports.send_reply") as send_reply:
            message = post_operator_message(
                context=self.context,
                conversation=self.conversation,
                text="Здравствуйте",
            )

        self.assertEqual(message.author_type, MessageAuthor.OPERATOR)
        self.assertEqual(message.text, "Здравствуйте")
        self.assertIsNotNone(message.gateway_command_id)
        self.assertEqual(message.delivery_status, "queued")
        self.assertEqual(message.external_id, "")
        send_reply.assert_not_called()

        event = OutboxEvent.objects.get(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
            aggregate_id=str(message.id),
        )
        self.assertEqual(
            OutboxEvent.objects.filter(
                event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
                aggregate_id=str(message.id),
            ).count(),
            1,
        )
        self.assertEqual(event.ownership, EventOwnership.TENANT)
        self.assertEqual(event.organization_id, self.organization.id)
        self.assertEqual(event.membership_id, self.context.membership_id)
        self.assertEqual(event.actor_user_id, self.owner.id)
        self.assertEqual(event.actor_kind, "HUMAN")
        self.assertTrue(event.correlation_id)
        self.assertEqual(event.aggregate_type, "Message")
        self.assertEqual(event.aggregate_id, str(message.id))

        command = event.payload["command"]
        self.assertEqual(event.payload["integration_id"], self.integration.id)
        self.assertEqual(command["schema"], "intercom-gw.delivery-command.v1")
        self.assertEqual(command["command_id"], str(message.gateway_command_id))
        self.assertEqual(command["source_id"], "tg-studio-main")
        self.assertEqual(command["recipient"], {
            "external_chat_id": "chat-1",
            "external_user_id": "user-1",
        })
        self.assertEqual(command["message"], {"kind": "text", "text": "Здравствуйте"})
        uuid.UUID(command["command_id"])
        self.assertNotIn("gateway-secret", str(event.payload))
        self.assertNotIn("Authorization", str(event.payload))
        self.assertNotIn("base_url", event.payload)
        self.assertNotIn("gateway.example.test", str(event.payload))

        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.expected_responder, ExpectedResponder.CUSTOMER)

    def test_gateway_operator_reply_api_returns_201_after_local_commit(self) -> None:
        with mock.patch("chatballs.conversations.services.transports.send_reply") as send_reply:
            response = self.client.post(
                f"/api/v1/conversations/{self.conversation.id}/messages/",
                {"text": "HTTP reply"},
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        message_id = response.json()["message"]["id"]
        self.assertTrue(Message.objects.filter(id=message_id, text="HTTP reply").exists())
        self.assertTrue(
            OutboxEvent.objects.filter(
                event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
                aggregate_id=str(message_id),
            ).exists()
        )
        send_reply.assert_not_called()

    def test_gateway_enqueue_failure_rolls_back_message_and_conversation_state(self) -> None:
        old_last_activity = self.conversation.last_activity_at

        with (
            mock.patch(
                "chatballs.conversations.gateway_delivery.enqueue_event",
                side_effect=RuntimeError("outbox unavailable"),
            ),
            self.assertRaises(RuntimeError),
        ):
            post_operator_message(
                context=self.context,
                conversation=self.conversation,
                text="Не должно сохраниться",
            )

        self.assertFalse(
            Message.objects.filter(
                conversation=self.conversation,
                text="Не должно сохраниться",
            ).exists()
        )
        self.assertFalse(
            Message.objects.filter(
                conversation=self.conversation,
                gateway_command_id__isnull=False,
            ).exists()
        )
        self.assertFalse(
            OutboxEvent.objects.filter(
                event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
            ).exists()
        )
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.expected_responder, ExpectedResponder.OPERATOR)
        self.assertEqual(self.conversation.last_activity_at, old_last_activity)

    def test_gateway_reply_rejects_missing_routing_without_partial_rows(self) -> None:
        self.integration.config = {"base_url": "https://gateway.example.test/"}
        self.integration.save(update_fields=["config"])
        self.conversation.external_chat_id = ""
        self.conversation.save(update_fields=["external_chat_id"])

        with self.assertRaises(GatewayDeliveryError):
            post_operator_message(
                context=self.context,
                conversation=self.conversation,
                text="Нет маршрута",
            )

        self.assertFalse(Message.objects.filter(conversation=self.conversation).exists())
        self.assertFalse(OutboxEvent.objects.filter(aggregate_type="Message").exists())

    def test_telegram_operator_reply_keeps_synchronous_transport_path(self) -> None:
        telegram = Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.TELEGRAM,
            name="Telegram source",
            secret="telegram-secret",
            channel=self.channel,
        )
        contact = self.organization.contacts.create(name="Иван")
        ConnectionIdentity.objects.create(
            contact=contact,
            connection=telegram,
            external_user_id="telegram-user",
        )
        conversation = Conversation.objects.create(
            organization=self.organization,
            channel=self.channel,
            connection=telegram,
            contact=contact,
            external_chat_id="telegram-chat",
            control_mode=ControlMode.HUMAN,
            expected_responder=ExpectedResponder.OPERATOR,
            assigned_operator=self.owner,
        )

        with (
            tenant_atomic(self.context),
            mock.patch(
                "chatballs.conversations.services.transports.send_reply",
                return_value=True,
            ) as send_reply,
        ):
            message = post_operator_message(
                context=self.context,
                conversation=conversation,
                text="Telegram reply",
            )

        self.assertEqual(message.text, "Telegram reply")
        self.assertIsNone(message.gateway_command_id)
        self.assertEqual(message.delivery_status, "")
        send_reply.assert_called_once_with(
            telegram,
            chat_id="telegram-chat",
            user_id="telegram-user",
            text="Telegram reply",
        )
        self.assertFalse(
            OutboxEvent.objects.filter(
                event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
                aggregate_id=str(message.id),
            ).exists()
        )
