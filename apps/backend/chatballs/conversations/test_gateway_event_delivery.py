from __future__ import annotations

import json
from datetime import timedelta
from unittest import mock
from urllib.error import URLError

from django.apps import apps
from django.conf import settings
from django.db import connections
from django.test import SimpleTestCase, TransactionTestCase
from django.utils import timezone

from chatballs.channels.models import Channel
from chatballs.conversations.gateway_event_handlers import (
    GatewayDeliveryError,
    handle_gateway_delivery_command_requested,
)
from chatballs.conversations.gateway_http import send_delivery_command
from chatballs.events.handlers import _OWN_TRANSACTION, dispatch
from chatballs.events.models import EventOwnership, OutboxEvent, OutboxStatus
from chatballs.events.services import claim_next_outbox_event, release_stale_processing
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import HumanUser, Organization
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.testing import tenant_context_for

COMMAND = {
    "schema": "intercom-gw.delivery-command.v1",
    "command_id": "8b9e7674-1be4-4bc4-9878-2b1dded3e65a",
    "source_id": "tg-studio-main",
    "recipient": {
        "external_chat_id": "chat-1",
        "external_user_id": "user-1",
    },
    "message": {"kind": "text", "text": "  keep whitespace \n"},
}


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self.body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class GatewayHttpClientTests(SimpleTestCase):
    def test_accepted_202_sends_exact_command_and_gateway_headers(self) -> None:
        response = FakeResponse(
            202,
            json.dumps({"accepted": True, "command_id": COMMAND["command_id"]}).encode(),
        )
        with mock.patch("urllib.request.urlopen", return_value=response) as urlopen:
            send_delivery_command(
                base_url="https://gateway.example.test/",
                secret="gateway-secret",
                command=COMMAND,
            )

        request, = urlopen.call_args.args
        self.assertEqual(request.full_url, "https://gateway.example.test/delivery-commands")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer gateway-secret")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(request.data.decode("utf-8")), COMMAND)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], settings.CHATBALLS_GATEWAY_DELIVERY_TIMEOUT_SECONDS)

    def test_non_202_or_invalid_response_is_rejected(self) -> None:
        responses = [
            FakeResponse(200, b'{"accepted": true, "command_id": "8b9e7674-1be4-4bc4-9878-2b1dded3e65a"}'),
            FakeResponse(202, b'{"accepted": false, "command_id": "8b9e7674-1be4-4bc4-9878-2b1dded3e65a"}'),
            FakeResponse(202, b'{"accepted": true, "command_id": "other"}'),
            FakeResponse(202, b"not-json"),
            FakeResponse(202, b"[]"),
        ]

        for response in responses:
            with self.subTest(response=response.status, body=response.body):
                with mock.patch("urllib.request.urlopen", return_value=response):
                    with self.assertRaises(GatewayDeliveryError):
                        send_delivery_command(
                            base_url="https://gateway.example.test",
                            secret="gateway-secret",
                            command=COMMAND,
                        )

    def test_network_error_does_not_expose_secret_or_command(self) -> None:
        with mock.patch("urllib.request.urlopen", side_effect=URLError("offline")):
            with self.assertRaises(GatewayDeliveryError) as raised:
                send_delivery_command(
                    base_url="https://gateway.example.test",
                    secret="gateway-secret",
                    command=COMMAND,
                )

        self.assertNotIn("gateway-secret", str(raised.exception))
        self.assertNotIn(COMMAND["message"]["text"], str(raised.exception))
        self.assertNotIn(COMMAND["command_id"], str(raised.exception))


class GatewayEventHandlerTests(TransactionTestCase):
    databases = {"default", "platform"}
    reset_sequences = True

    def setUp(self) -> None:
        outbox_db_patch = mock.patch("chatballs.events.services.OUTBOX_DB", "default")
        outbox_db_patch.start()
        self.addCleanup(outbox_db_patch.stop)
        bootstrap_owner(email="gateway-worker@example.com", password="temporary-password")
        self.organization = Organization.objects.get(slug="demo")
        self.owner = HumanUser.objects.get(email="gateway-worker@example.com")
        self.channel = Channel.objects.create(
            organization=self.organization,
            code="gateway-worker",
            name="Gateway worker",
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
        self.context = tenant_context_for(self.owner, self.organization)

    def payload(self, **overrides: object) -> dict:
        payload = {"integration_id": self.integration.id, "command": dict(COMMAND)}
        payload.update(overrides)
        return payload

    def test_conversations_ready_registers_gateway_handler_with_own_transaction(self) -> None:
        apps.get_app_config("conversations").ready()

        self.assertIn("gateway.delivery_command.requested.v1", _OWN_TRANSACTION)

    def test_integration_is_loaded_in_tenant_context_and_network_runs_after_transaction(self) -> None:
        observed: list[tuple[bool, int | None]] = []

        def sender(*, base_url: str, secret: str, command: dict) -> None:
            observed.append(
                (connections["default"].in_atomic_block, Integration.objects.get(pk=self.integration.id).organization_id)
            )
            self.assertEqual(base_url, "https://gateway.example.test/")
            self.assertEqual(secret, "gateway-secret")
            self.assertEqual(command, COMMAND)

        with mock.patch(
            "chatballs.conversations.gateway_event_handlers.send_delivery_command",
            side_effect=sender,
        ):
            handle_gateway_delivery_command_requested(self.payload(), self.context)

        self.assertEqual(observed, [(False, self.organization.id)])

    def test_wrong_organization_integration_is_rejected(self) -> None:
        other = Organization.objects.create(slug="other-gateway-org", name="Other")
        other_integration = Integration.objects.create(
            organization=other,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.GATEWAY,
            name="Other gateway",
            secret="other-secret",
            config={"source_id": "tg-studio-main", "base_url": "https://other.example.test"},
        )

        with self.assertRaises(GatewayDeliveryError):
            handle_gateway_delivery_command_requested(
                {"integration_id": other_integration.id, "command": dict(COMMAND)},
                self.context,
            )

    def test_non_gateway_or_inactive_integration_is_rejected(self) -> None:
        for provider, is_active in (
            (IntegrationProvider.TELEGRAM, True),
            (IntegrationProvider.GATEWAY, False),
        ):
            with self.subTest(provider=provider, is_active=is_active):
                integration = Integration.objects.create(
                    organization=self.organization,
                    kind=IntegrationKind.MESSENGER,
                    provider=provider,
                    name=f"Invalid {provider} {is_active}",
                    secret="secret",
                    config={"source_id": "tg-studio-main", "base_url": "https://gateway.example.test"},
                    is_active=is_active,
                )
                with self.assertRaises(GatewayDeliveryError):
                    handle_gateway_delivery_command_requested(
                        {"integration_id": integration.id, "command": dict(COMMAND)},
                        self.context,
                    )

    def test_source_mismatch_is_rejected_without_http(self) -> None:
        command = dict(COMMAND)
        command["source_id"] = "different-source"
        with mock.patch(
            "chatballs.conversations.gateway_event_handlers.send_delivery_command"
        ) as sender:
            with self.assertRaises(GatewayDeliveryError):
                handle_gateway_delivery_command_requested(
                    self.payload(command=command), self.context
                )
        sender.assert_not_called()

    def test_crash_after_202_reclaims_and_resends_same_persisted_command(self) -> None:
        event = OutboxEvent.objects.create(
            aggregate_type="Message",
            aggregate_id="message-1",
            event_type="gateway.delivery_command.requested.v1",
            payload=self.payload(),
            ownership=EventOwnership.TENANT,
            organization=self.organization,
            actor_kind="SYSTEM",
            correlation_id="gateway-crash-test",
            next_attempt_at=timezone.now() - timedelta(seconds=1),
        )
        sent_commands: list[dict] = []

        def accepted_sender(*, base_url: str, secret: str, command: dict) -> None:
            sent_commands.append(command)

        with mock.patch(
            "chatballs.conversations.gateway_event_handlers.send_delivery_command",
            side_effect=accepted_sender,
        ):
            first_claim = claim_next_outbox_event()
            self.assertIsNotNone(first_claim)
            dispatch(first_claim)

        OutboxEvent.objects.filter(pk=event.id).update(
            next_attempt_at=timezone.now() - timedelta(seconds=1)
        )
        self.assertEqual(release_stale_processing(), 1)

        with mock.patch(
            "chatballs.conversations.gateway_event_handlers.send_delivery_command",
            side_effect=accepted_sender,
        ):
            second_claim = claim_next_outbox_event()
            self.assertIsNotNone(second_claim)
            dispatch(second_claim)

        self.assertEqual(sent_commands, [COMMAND, COMMAND])
        self.assertEqual(sent_commands[0]["command_id"], COMMAND["command_id"])
        OutboxEvent.objects.filter(pk=event.id).update(
            status=OutboxStatus.PROCESSED, processed_at=timezone.now()
        )
        self.assertEqual(
            OutboxEvent.objects.get(pk=event.id).status,
            OutboxStatus.PROCESSED,
        )
