"""Opt-in network smoke: real Fastify TG/MAX HTTP <-> Django live server.

Requires the private Compose smoke services. No network to GREEN-API,
no production data, no production credentials, no public host ports.
"""

import json
import uuid
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.test import LiveServerTestCase, override_settings

from chatballs.ai.models import AIAgent, AIAgentStatus
from chatballs.channels.models import Channel
from chatballs.conversations.ai_turn import AI_TURN_REQUESTED, _begin
from chatballs.conversations.ai_turn_completion import _commit_if_current
from chatballs.conversations.ai_turn_result import store_answer
from chatballs.conversations.gateway_delivery import GATEWAY_DELIVERY_COMMAND_REQUESTED
from chatballs.conversations.models import AiTurnState, ControlMode, Message, MessageAuthor
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.native_mirror.models import (
    MirrorReceiptStatus, NativeMirrorConversationState,
    NativeMirrorPublication, NativeMirrorReceipt, PublicationStatus,
)
from chatballs.testing import system_tenant_context
from chatballs.tenancy.database import tenant_atomic

SECRET = "synthetic-network-only"
WEBHOOK_SECRET = "synthetic-webhook-test-only"
GATEWAYS = {"TG": "http://native-smoke-tg:3000", "MAX": "http://native-smoke-max:3000"}


def http_json(url, payload=None, headers=None):
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url, data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST" if data is not None else "GET",
    )
    try:
        with urlopen(request, timeout=8) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


@override_settings(ALLOWED_HOSTS=["native-smoke-runner", "localhost", "127.0.0.1"])
class NativeMirrorLiveNetworkSmoke(LiveServerTestCase):
    host = "0.0.0.0"

    def setUp(self):
        owner = bootstrap_owner(
            email="network-native-smoke@example.test", password="temporary-password",
        )
        self.organization = owner.organization
        self.owner = owner.owner
        self.context = system_tenant_context(self.organization)
        # The Django LiveServer listens on an ephemeral port on all private
        # interfaces. No Docker host ports are published for the runner.
        self.chatballs_url = (
            f"http://native-smoke-runner:{urlsplit(self.live_server_url).port}"
        )

    def make_integration(self, transport, mode="ENABLED"):
        channel = Channel.objects.create(
            organization=self.organization, code=f"net-{transport.lower()}",
            name=f"Network Smoke {transport}",
        )
        AIAgent.objects.create(
            channel=channel, name="Synthetic AI", model="openai/gpt-4o-mini",
            status=AIAgentStatus.ACTIVE,
        )
        integration = Integration.objects.create(
            organization=self.organization, channel=channel,
            kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.GATEWAY,
            name=f"Network Gateway {transport}", secret=SECRET,
            config={
                "source_id": f"{transport.lower()}-network-smoke",
                "base_url": GATEWAYS[transport],
                "native_operator_user_id": self.owner.id,
                "native_mirror_mode": mode,
            },
        )
        self.configure(transport, integration)
        return integration

    def configure(self, transport, integration, *, secret=SECRET, fail_next=False):
        status, body = http_json(GATEWAYS[transport] + "/__smoke/configure", {
            "base_url": self.chatballs_url,
            "integration_id": integration.id,
            "integration_secret": secret,
            "fail_next": fail_next,
        })
        self.assertEqual((status, body), (200, {"accepted": True}))

    def state(self, transport):
        status, body = http_json(GATEWAYS[transport] + "/__smoke/state")
        self.assertEqual(status, 200)
        return body

    def callback(self, transport, *, native=False, ident="1", auth=WEBHOOK_SECRET):
        event_type = "outgoingMessageReceived" if native else "incomingMessageReceived"
        event = {
            "typeWebhook": event_type,
            "timestamp": int(datetime(2026, 10, 12, 14, 0, tzinfo=UTC).timestamp()),
            "idMessage": f"{transport.lower()}-{event_type}-{ident}",
            "senderData": {
                "chatId": f"{transport.lower()}-smoke-chat",
                "sender": "synthetic-account",
                "senderName": "Synthetic User",
                **({"chatType": "user"} if transport == "MAX" else {}),
            },
            "messageData": {
                "typeMessage": "textMessage",
                "textMessageData": {"textMessage": (
                    "Synthetic operator reply" if native else "Synthetic customer question"
                )},
            },
        }
        route = "/tg-gateway/callback/tg" if transport == "TG" else "/max-gateway/callback/max"
        return http_json(
            GATEWAYS[transport] + route, event,
            headers={"x-green-api-secret": auth},
        )[0]

    def customer(self, transport, integration, ident="1"):
        self.assertEqual(self.callback(transport, ident=ident), 202)
        return Message.objects.get(
            conversation__connection=integration,
            author_type=MessageAuthor.CONTACT,
            external_id=f"{transport.lower()}-incomingMessageReceived-{ident}",
        )

    def queue_ai_reply(self, customer, text):
        job = OutboxEvent.objects.get(
            event_type=AI_TURN_REQUESTED, payload__messageId=customer.id,
        )
        with tenant_atomic(self.context):
            turn = _begin(
                message_id=customer.id, user_id="synthetic-account",
                is_new=False, context=self.context,
                mirror_revision=job.payload["mirrorRevision"],
            )
        self.assertIsNotNone(turn)
        self.assertEqual(_commit_if_current(
            turn=turn, context=self.context,
            persist=lambda: store_answer(
                turn=turn, context=self.context, text=text,
            ),
        ), text)
        message = Message.objects.get(
            conversation=customer.conversation,
            author_type=MessageAuthor.AI,
            text=text,
        )
        event = OutboxEvent.objects.get(
            aggregate_id=str(message.id),
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
        )
        return message, event

    def test_http_shadow_and_enabled_reengagement(self):
        for transport in GATEWAYS:
            with self.subTest(transport=transport):
                integration = self.make_integration(transport, "SHADOW")
                first = self.customer(transport, integration)
                self.assertEqual(self.callback(transport, native=True), 202)
                first.refresh_from_db()
                self.assertEqual(first.ai_turn_state, AiTurnState.PENDING)
                self.assertFalse(NativeMirrorReceipt.objects.filter(
                    integration=integration,
                ).exists())

                config = dict(integration.config)
                config["native_mirror_mode"] = "ENABLED"
                integration.config = config
                integration.save(update_fields=["config"])
                self.assertEqual(self.callback(transport, native=True), 202)
                self.assertEqual(self.callback(transport, native=True), 202)
                first.refresh_from_db()
                self.assertEqual(first.ai_turn_state, AiTurnState.DONE)
                self.assertEqual(
                    NativeMirrorConversationState.objects.get(
                        conversation=first.conversation,
                    ).revision, 1,
                )
                self.assertEqual(NativeMirrorReceipt.objects.filter(
                    integration=integration, status=MirrorReceiptStatus.STORED,
                ).count(), 1)
                first.conversation.refresh_from_db()
                self.assertEqual(first.conversation.control_mode, ControlMode.AI)

                second = self.customer(transport, integration, ident="2")
                turn_event = OutboxEvent.objects.get(
                    event_type=AI_TURN_REQUESTED, payload__messageId=second.id,
                )
                self.assertEqual(turn_event.payload["mirrorRevision"], 1)

    def test_http_webhook_and_downstream_auth_with_retry(self):
        for transport in GATEWAYS:
            with self.subTest(transport=transport):
                integration = self.make_integration(transport)
                self.customer(transport, integration)
                self.assertEqual(self.callback(
                    transport, native=True, auth="wrong-webhook-key",
                ), 403)
                self.assertFalse(NativeMirrorReceipt.objects.filter(
                    integration=integration,
                ).exists())

                self.configure(transport, integration, secret="wrong-chatballs-secret")
                self.assertEqual(self.callback(transport, native=True), 202)
                self.assertEqual(self.state(transport)["last_failure"],
                                 "operator_mirror_delivery_failed")
                self.assertFalse(NativeMirrorReceipt.objects.filter(
                    integration=integration,
                ).exists())

                self.configure(transport, integration, fail_next=True)
                self.assertEqual(self.callback(transport, native=True), 202)
                self.assertEqual(self.state(transport)["last_failure"],
                                 "operator_mirror_delivery_failed")
                self.assertEqual(self.callback(transport, native=True), 202)
                self.assertEqual(self.state(transport)["accepted"], 0)
                self.assertEqual(NativeMirrorReceipt.objects.filter(
                    integration=integration, status=MirrorReceiptStatus.STORED,
                ).count(), 1)
                self.assertEqual(self.callback(transport, native=True), 202)
                self.assertEqual(NativeMirrorReceipt.objects.filter(
                    integration=integration,
                ).count(), 1)

    def test_http_outbound_claim_before_and_after_native_reply(self):
        for transport in GATEWAYS:
            with self.subTest(transport=transport):
                integration = self.make_integration(transport)
                first = self.customer(transport, integration)
                message, event = self.queue_ai_reply(
                    first, "Synthetic queued AI reply",
                )
                before = len(self.state(transport)["outbound_commands"])
                self.assertEqual(self.callback(transport, native=True), 202)
                dispatch(event)
                self.assertEqual(len(self.state(transport)["outbound_commands"]), before)
                message.refresh_from_db()
                self.assertEqual(message.delivery_status, "suppressed")
                self.assertEqual(NativeMirrorPublication.objects.get(
                    message=message,
                ).status, PublicationStatus.SUPPRESSED)

                # Reverse direction: Chatballs -> real Fastify HTTP succeeds
                # when claimed first. A later native answer does not revoke
                # an already network-visible command or make retries unsafe.
                second = self.customer(transport, integration, ident="2")
                next_message, next_event = self.queue_ai_reply(
                    second, "Synthetic publish-before-native",
                )
                before = len(self.state(transport)["outbound_commands"])
                dispatch(next_event)
                dispatched = self.state(transport)["outbound_commands"]
                self.assertEqual(len(dispatched), before + 1)
                self.assertEqual(dispatched[-1]["commandId"],
                                 str(next_message.gateway_command_id))
                self.assertEqual(NativeMirrorPublication.objects.get(
                    message=next_message,
                ).status, PublicationStatus.CLAIMED)
                self.assertEqual(self.callback(
                    transport, native=True, ident="2",
                ), 202)
                dispatch(next_event)
                self.assertEqual(len(
                    self.state(transport)["outbound_commands"],
                ), before + 2)
                self.assertEqual(NativeMirrorPublication.objects.get(
                    message=next_message,
                ).status, PublicationStatus.CLAIMED)

    def test_http_gateway_outbound_authorization_and_source(self):
        for transport in GATEWAYS:
            with self.subTest(transport=transport):
                self.make_integration(transport)
                data = {
                    "schema": "intercom-gw.delivery-command.v1",
                    "command_id": str(uuid.uuid4()),
                    "source_id": f"{transport.lower()}-network-smoke",
                    "recipient": {
                        "external_chat_id": f"{transport.lower()}-smoke-chat",
                        "external_user_id": None,
                    },
                    "message": {"kind": "text", "text": "Synthetic outbound"},
                }
                endpoint = GATEWAYS[transport] + "/delivery-commands"
                self.assertEqual(http_json(
                    endpoint, data, headers={"Authorization": "Bearer wrong"},
                )[0], 401)
                data["source_id"] = "wrong-source"
                self.assertEqual(http_json(
                    endpoint, data, headers={"Authorization": f"Bearer {SECRET}"},
                )[0], 409)
                data["source_id"] = f"{transport.lower()}-network-smoke"
                self.assertEqual(http_json(
                    endpoint, data, headers={"Authorization": f"Bearer {SECRET}"},
                )[0], 202)
                self.assertEqual(
                    self.state(transport)["outbound_commands"][-1]["commandId"],
                    data["command_id"],
                )
