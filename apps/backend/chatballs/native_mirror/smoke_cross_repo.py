"""Opt-in cross-repo contract smoke: real TG/MAX Gateway output -> Chatballs API.

Not automatically collected by the normal 'test_*.py' suite. Generate the
bundle using intercom-gw/tools/native-mirror-smoke-bundle.mjs first.
Only disposable PostgreSQL and synthetic identities are supported.
"""

import json
import os
import uuid
from pathlib import Path
from unittest import mock

from django.test import TransactionTestCase
from rest_framework.test import APIClient

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
    MirrorReceiptStatus, NativeMirrorConversationState, NativeMirrorPublication,
    NativeMirrorReceipt, PublicationStatus,
)
from chatballs.testing import system_tenant_context
from chatballs.tenancy.database import tenant_atomic


BUNDLE_ENV = "CHATBALLS_NATIVE_SMOKE_BUNDLE"
SCHEMA = "chatballs.native-mirror.cross-repo-smoke.v1"
TEST_SECRET = "synthetic-cross-repo-only"


def read_bundle():
    path = os.environ.get(BUNDLE_ENV)
    if not path:
        raise RuntimeError(f"{BUNDLE_ENV} is required for this opt-in smoke")
    bundle = json.loads(Path(path).read_text(encoding="utf8"))
    if bundle.get("schema") != SCHEMA or bundle.get("fixture_only") is not True:
        raise ValueError("Unexpected or non-synthetic Native Mirror smoke bundle")
    cases = bundle.get("cases")
    if not isinstance(cases, list) or sorted(c.get("transport") for c in cases) != [
        "MAX", "TG",
    ]:
        raise ValueError("Smoke bundle must contain exactly one TG and one MAX case")
    for case in cases:
        native = case["operator_mirror"]
        if native.get("schema") != "intercom-gw.chatballs.operator-mirror.v1":
            raise ValueError("Unexpected Gateway operator-mirror contract")
        if native.get("source_id") != case.get("source_id"):
            raise ValueError("Cross-repo source mismatch")
        if native.get("origin") != {"provider_event_type": "outgoingMessageReceived"}:
            raise ValueError("Missing trusted native provider event classification")
        if len(case.get("customer_inbound", [])) != 2:
            raise ValueError("Exactly two synthetic customer events are needed")
        if case.get("api_echo_forwarded") is not False:
            raise ValueError("API echo leaked to native bridge")
    return cases


class NativeMirrorCrossRepoSmoke(TransactionTestCase):
    """Real DRF ingress and DB state, with the event produced in intercom-gw."""

    def setUp(self):
        self.cases = read_bundle()
        owner = bootstrap_owner(
            email="cross-repo-smoke@example.test", password="temporary-password",
        )
        self.organization = owner.organization
        self.owner = owner.owner
        self.context = system_tenant_context(self.organization)
        self.client = APIClient()

    def _connection(self, case, mode="ENABLED"):
        channel = Channel.objects.create(
            organization=self.organization,
            code=f"cross-repo-{case['transport'].lower()}",
            name="Synthetic Cross Repo",
        )
        AIAgent.objects.create(
            channel=channel, name="Synthetic AI", model="openai/gpt-4o-mini",
            status=AIAgentStatus.ACTIVE,
        )
        return Integration.objects.create(
            organization=self.organization,
            kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.GATEWAY,
            channel=channel, name="Synthetic Gateway",
            secret=TEST_SECRET,
            config={
                "source_id": case["source_id"],
                "base_url": "https://gateway.invalid/",
                "native_operator_user_id": self.owner.id,
                "native_mirror_mode": mode,
            },
        )

    def _post(self, integration, path, body, secret=TEST_SECRET):
        return self.client.post(
            f"/api/v1/gateway/integrations/{integration.id}/{path}/",
            data=body, format="json", HTTP_AUTHORIZATION=f"Bearer {secret}",
        )

    def _customer(self, integration, case, index=0):
        response = self._post(
            integration, "inbound", case["customer_inbound"][index],
        )
        self.assertEqual(response.status_code, 202, response.content)
        return Message.objects.get(
            author_type=MessageAuthor.CONTACT,
            conversation__connection=integration,
            external_id=case["customer_inbound"][index]["message"]["external_message_id"],
        )

    def _native(self, integration, case):
        return self._post(integration, "operator-mirror", case["operator_mirror"])

    def _revision(self, conversation):
        return NativeMirrorConversationState.objects.get(
            conversation=conversation,
        ).revision

    def test_shadow_never_changes_dialogue_or_running_ai(self):
        for case in self.cases:
            with self.subTest(transport=case["transport"]):
                integration = self._connection(case, mode="SHADOW")
                inbound = self._customer(integration, case)
                revision_before = OutboxEvent.objects.filter(
                    event_type=AI_TURN_REQUESTED,
                    payload__messageId=inbound.id,
                ).count()
                self.assertEqual(revision_before, 1)
                self.assertEqual(self._native(integration, case).status_code, 202)
                inbound.refresh_from_db()
                self.assertEqual(inbound.ai_turn_state, AiTurnState.PENDING)
                self.assertFalse(NativeMirrorReceipt.objects.filter(
                    integration=integration,
                ).exists())
                self.assertFalse(Message.objects.filter(
                    author_type=MessageAuthor.OPERATOR,
                    conversation__connection=integration,
                ).exists())
                self.assertFalse(NativeMirrorConversationState.objects.filter(
                    conversation=inbound.conversation,
                ).exists())

    def test_enabled_supersedes_old_turn_dedupes_and_reengages_ai(self):
        for case in self.cases:
            with self.subTest(transport=case["transport"]):
                integration = self._connection(case)
                first = self._customer(integration, case)
                conversation = first.conversation
                self.assertEqual(self._native(integration, case).status_code, 202)
                self.assertEqual(self._native(integration, case).status_code, 202)
                first.refresh_from_db()
                self.assertEqual(first.ai_turn_state, AiTurnState.DONE)
                self.assertEqual(self._revision(conversation), 1)
                self.assertEqual(NativeMirrorReceipt.objects.filter(
                    integration=integration, status=MirrorReceiptStatus.STORED,
                ).count(), 1)
                operator = Message.objects.get(
                    author_type=MessageAuthor.OPERATOR,
                    conversation=conversation,
                )
                self.assertEqual(operator.author_user_id, self.owner.id)
                self.assertEqual(operator.text, "Synthetic native operator reply")
                conversation.refresh_from_db()
                self.assertEqual(conversation.control_mode, ControlMode.AI)

                second = self._customer(integration, case, index=1)
                queued = OutboxEvent.objects.get(
                    event_type=AI_TURN_REQUESTED,
                    payload__messageId=second.id,
                )
                self.assertEqual(queued.payload["mirrorRevision"], 1)
                self.assertEqual(second.ai_turn_state, AiTurnState.PENDING)

    def test_missing_conversation_is_persisted_then_replayed(self):
        for case in self.cases:
            with self.subTest(transport=case["transport"]):
                integration = self._connection(case)
                self.assertEqual(self._native(integration, case).status_code, 202)
                receipt = NativeMirrorReceipt.objects.get(integration=integration)
                self.assertEqual(receipt.status, MirrorReceiptStatus.PENDING)
                self.assertTrue(receipt.pending_text)
                customer = self._customer(integration, case)
                self.assertEqual(self._native(integration, case).status_code, 202)
                receipt.refresh_from_db()
                self.assertEqual(receipt.status, MirrorReceiptStatus.STORED)
                self.assertEqual(receipt.conversation_id, customer.conversation_id)
                self.assertEqual(self._revision(customer.conversation), 1)

    def test_correlated_self_echo_does_not_interrupt_pending_ai(self):
        for case in self.cases:
            with self.subTest(transport=case["transport"]):
                integration = self._connection(case)
                customer = self._customer(integration, case)
                Message.objects.create(
                    conversation=customer.conversation,
                    author_type=MessageAuthor.AI,
                    text="Synthetic own API send",
                    gateway_command_id=uuid.uuid4(),
                    external_id=case["operator_mirror"]["message"]["external_message_id"],
                )
                self.assertEqual(self._native(integration, case).status_code, 202)
                receipt = NativeMirrorReceipt.objects.get(integration=integration)
                self.assertEqual(receipt.status, MirrorReceiptStatus.SELF_ECHO)
                self.assertFalse(NativeMirrorConversationState.objects.filter(
                    conversation=customer.conversation,
                ).exists())
                customer.refresh_from_db()
                self.assertEqual(customer.ai_turn_state, AiTurnState.PENDING)

    def test_post_publish_native_reply_suppresses_stale_gateway_outbox(self):
        for case in self.cases:
            with self.subTest(transport=case["transport"]):
                integration = self._connection(case)
                first = self._customer(integration, case)
                job = OutboxEvent.objects.get(
                    event_type=AI_TURN_REQUESTED, payload__messageId=first.id,
                )
                with tenant_atomic(self.context):
                    turn = _begin(
                        message_id=first.id,
                        user_id=case["customer_inbound"][0]["sender"]["external_user_id"],
                        is_new=False, context=self.context,
                        mirror_revision=job.payload["mirrorRevision"],
                    )
                self.assertIsNotNone(turn)
                self.assertEqual(_commit_if_current(
                    turn=turn, context=self.context,
                    persist=lambda: store_answer(
                        turn=turn, context=self.context, text="Synthetic AI draft",
                    ),
                ), "Synthetic AI draft")
                ai = Message.objects.get(
                    author_type=MessageAuthor.AI, text="Synthetic AI draft",
                    conversation=first.conversation,
                )
                outbound = OutboxEvent.objects.get(
                    event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
                    aggregate_id=str(ai.id),
                )
                self.assertEqual(
                    NativeMirrorPublication.objects.get(message=ai).status,
                    PublicationStatus.QUEUED,
                )
                self.assertEqual(self._native(integration, case).status_code, 202)
                with mock.patch(
                    "chatballs.conversations.gateway_event_handlers.send_delivery_command",
                ) as send:
                    dispatch(outbound)
                    send.assert_not_called()
                ai.refresh_from_db()
                self.assertEqual(ai.delivery_status, "suppressed")
                self.assertEqual(
                    NativeMirrorPublication.objects.get(message=ai).status,
                    PublicationStatus.SUPPRESSED,
                )
                response = self.client.get(
                    f"/api/v1/gateway/integrations/{integration.id}/operator-mirror/"
                )
                self.assertNotEqual(response.status_code, 202)

    def test_wrong_auth_or_source_never_writes_native_receipt(self):
        for case in self.cases:
            with self.subTest(transport=case["transport"]):
                integration = self._connection(case)
                self._customer(integration, case)
                invalid_auth = self._post(
                    integration, "operator-mirror", case["operator_mirror"],
                    secret="wrong-synthetic-secret",
                )
                self.assertEqual(invalid_auth.status_code, 401)
                body = json.loads(json.dumps(case["operator_mirror"]))
                body["source_id"] = "invalid-source"
                invalid_source = self._post(
                    integration, "operator-mirror", body,
                )
                self.assertEqual(invalid_source.status_code, 409)
                self.assertFalse(NativeMirrorReceipt.objects.filter(
                    integration=integration,
                ).exists())
