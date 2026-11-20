"""The Connector AI route, durable claim, and authenticated callback round trip."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event
from unittest.mock import patch

from django.db import close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase

from chatballs.ai.models import AIAgent, AIAgentStatus
from chatballs.ai.runtime import HANDOFF_TOKEN
from chatballs.api_connector.delivery_correlation import lock_command_message
from chatballs.api_connector.observed_test_fixture import ObservedOutgoingFixture
from chatballs.api_connector.outbound import CONNECTOR_OUTBOUND_REQUESTED
from chatballs.api_connector.payloads import ConnectorPayloadError
from chatballs.api_connector.testing_fake_adapter import FakeAdapter
from chatballs.conversations.ai_turn import AI_TURN_REQUESTED, _begin
from chatballs.conversations.ai_turn_completion import _commit_if_current
from chatballs.conversations.ai_turn_result import store_answer
from chatballs.conversations.models import (
    AiTurnState,
    ControlMode,
    Conversation,
    MessageAuthor,
)
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.identity.models import Organization
from chatballs.identity.operation_modes import OperationMode, lock_organization
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.native_mirror.models import NativeMirrorPublication, PublicationStatus
from chatballs.native_mirror.visibility import visible_messages
from chatballs.tenancy.database import set_local_tenant, tenant_atomic
from chatballs.testing import ai_answer, run_pending_ai_turns, system_tenant_context


class ConnectorAIOutboundTests(ObservedOutgoingFixture, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.context = system_tenant_context(self.organization)
        provider = Integration.objects.create(
            organization=self.organization, name="Demo", provider=IntegrationProvider.DEMO,
            kind=IntegrationKind.LLM_PROVIDER, secret="demo",
        )
        self.agent = AIAgent.objects.create(
            channel=self.integration.channel, provider_integration=provider, name="Test AI",
            status=AIAgentStatus.ACTIVE, model="demo",
        )

    def set_ai(self, enabled):
        result = self.client.patch(
            f"/api/v1/integrations/{self.integration.pk}/",
            {"config": {"connectorAiOutboundEnabled": enabled}}, format="json",
        )
        self.assertEqual(result.status_code, 200, result.data)

    def configure_transport(self, url="http://127.0.0.1:9081/v1/commands"):
        result = self.client.post(
            f"/api/v1/integrations/{self.integration.pk}/connector-transport/",
            {"url": url, "token": FakeAdapter.token}, format="json",
        )
        self.assertEqual(result.status_code, 200, result.data)

    def queue_reply(self, text="An AI reply"):
        conversation = self.open_conversation()
        self.assertEqual(conversation.control_mode, ControlMode.AI)
        with (ai_answer(text), patch("chatballs.conversations.transports.send_reply") as direct):
            self.assertEqual(run_pending_ai_turns(), 1)
            direct.assert_not_called()
        message = conversation.messages.get(author_type=MessageAuthor.AI)
        publication = NativeMirrorPublication.objects.get(message=message)
        self.assertEqual(publication.status, PublicationStatus.QUEUED)
        event = OutboxEvent.objects.get(
            event_type=CONNECTOR_OUTBOUND_REQUESTED, payload__message_id=message.pk,
        )
        return conversation, message, event

    def echo(self, command_id):
        return {
            "schema": "chatballs.api-connector.event.v1", "source_id": self.source,
            "event": {"id": "echo-ai", "type": "message.echo", "occurred_at": "2026-11-19T12:00:00Z"},
            "conversation": {"external_chat_id": "chat-1"},
            "echo": {"origin": "command_echo", "command_id": command_id, "external_message_id": "out-1"},
        }

    def receipt(self, command_id):
        return {
            "schema": "chatballs.api-connector.receipt.v1", "source_id": self.source,
            "event": {"id": "receipt-ai", "occurred_at": "2026-11-19T12:00:00Z"},
            "command_id": command_id, "status": "DELIVERED", "provider_message_id": "out-1",
        }

    def test_default_opt_in_transport_and_operation_mode_are_independent(self):
        self.set_ai(True)
        self.assertEqual(self.open_conversation(chat_id="no-transport").control_mode, ControlMode.PAUSED)
        self.configure_transport()
        self.set_ai(False)
        self.assertEqual(self.open_conversation(chat_id="opted-out", event_id="in-2").control_mode, ControlMode.PAUSED)
        self.set_ai(True)
        Organization.objects.filter(pk=self.organization.pk).update(operation_mode=OperationMode.OPERATORS_ONLY)
        self.assertEqual(self.open_conversation(chat_id="org-off", event_id="in-3").control_mode, ControlMode.PAUSED)
        self.assertFalse(OutboxEvent.objects.filter(event_type=AI_TURN_REQUESTED).exists())

    def test_external_executor_stays_in_operator_queue(self):
        self.configure_transport()
        self.set_ai(True)
        AIAgent.objects.filter(pk=self.agent.pk).update(execution_mode="external")
        with patch("chatballs.ai.external_agents.readiness.ready", return_value=True):
            self.assertEqual(self.open_conversation().control_mode, ControlMode.PAUSED)
        self.assertFalse(OutboxEvent.objects.filter(event_type=AI_TURN_REQUESTED).exists())

    def test_ai_command_real_http_ack_echo_and_receipt_with_mirror_off(self):
        self.assertEqual(self.set_mirror(False).status_code, 200)
        self.set_ai(True)
        with FakeAdapter(source_id=self.source) as adapter:
            self.configure_transport(adapter.url)
            conversation, message, event = self.queue_reply()
            command = event.payload["command"]
            command_id = command["command_id"]
            self.assertEqual(command["recipient"], {"external_chat_id": "chat-1", "external_user_id": "guest-1"})
            self.assertEqual(command["message"], {"kind": "text", "text": "An AI reply", "media": []})
            self.assertEqual(self.send(self.echo(command_id)).status_code, 409)
            self.assertEqual(self.send(self.receipt(command_id)).status_code, 409)
            self.assertFalse(conversation.domain_events.filter(event_type="PUBLIC_REPLY").exists())

            dispatch(event)
            dispatch(event)
            self.assertEqual(adapter.commands, [command])

        publication = NativeMirrorPublication.objects.get(message=message)
        self.assertEqual(publication.status, PublicationStatus.CLAIMED)
        self.assertEqual(conversation.domain_events.filter(event_type="PUBLIC_REPLY", actor_kind="AI").count(), 1)
        self.assertEqual(self.send(self.echo(command_id)).status_code, 202)
        message.refresh_from_db()
        self.assertEqual(message.connector_delivery["state"], "ADAPTER_ACCEPTED")
        self.assertEqual(self.send(self.receipt(command_id)).status_code, 202)
        self.assertEqual(self.send(self.receipt(command_id)).status_code, 202)
        message.refresh_from_db()
        self.assertEqual(message.connector_delivery["state"], "DELIVERED")
        self.assertEqual(message.connector_delivery["providerMessageId"], "out-1")
        self.assertEqual(conversation.messages.count(), 2)

    def test_mirror_suppresses_running_ai_and_next_inbound_stays_with_human(self):
        self.configure_transport()
        self.set_ai(True)
        conversation = self.open_conversation()
        message = conversation.messages.get()
        with tenant_atomic(self.context):
            turn = _begin(message_id=message.pk, user_id="guest-1", is_new=True,
                          context=self.context, mirror_revision=0)
        self.assertIsNotNone(turn)
        self.assertEqual(self.send(self.observed()).status_code, 202)
        self.assertIsNone(_commit_if_current(
            turn=turn, context=self.context,
            persist=lambda: store_answer(turn=turn, context=self.context, text="Stale reply"),
        ))
        message.refresh_from_db()
        self.assertEqual(message.ai_turn_state, AiTurnState.DONE)
        self.assertFalse(conversation.messages.filter(author_type=MessageAuthor.AI).exists())
        conversation.refresh_from_db()
        self.assertEqual(conversation.control_mode, ControlMode.HUMAN)
        self.assertEqual(
            conversation.domain_events.filter(event_type="ACCEPTED", actor_kind="HUMAN").count(), 1,
        )
        self.assertEqual(
            conversation.domain_events.filter(event_type="PUBLIC_REPLY", actor_kind="HUMAN").count(), 1,
        )
        self.assertEqual(self.send(self.incoming(event_id="in-2", external_id="guest-2")).status_code, 202)
        new_message = conversation.messages.get(external_id="guest-2")
        self.assertFalse(OutboxEvent.objects.filter(
            event_type=AI_TURN_REQUESTED, payload__messageId=new_message.pk,
        ).exists())

    def test_claimed_ai_callback_correlation_obeys_runtime_rls(self):
        self.configure_transport()
        self.set_ai(True)
        _, message, event = self.queue_reply()
        with patch("chatballs.api_connector.outbound._send_command"):
            dispatch(event)
        command_id = event.payload["command"]["command_id"]
        scoped = {"conflict_code": "echo_conflict", "connector_delivery__commandId": command_id}
        other = Organization.objects.create(name="Other organization", slug="other-connector-ai")
        self.integration.refresh_from_db(fields=["secret"])

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            set_local_tenant(other.pk)
            with self.assertRaisesRegex(ConnectorPayloadError, "not_found"):
                lock_command_message(self.integration, **scoped)
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            set_local_tenant(self.organization.pk)
            self.assertEqual(lock_command_message(self.integration, **scoped).pk, message.pk)

    @contextmanager
    def hold_connector_during_claim(self, event):
        worker_has_org_lock = Event()

        def lock_then_signal(organization_id):
            organization = lock_organization(organization_id)
            worker_has_org_lock.set()
            return organization

        def claim():
            close_old_connections()
            try:
                dispatch(event)
            finally:
                connections.close_all()

        with (ThreadPoolExecutor(max_workers=1) as executor,
              patch("chatballs.api_connector.outbound_ai.lock_organization", side_effect=lock_then_signal)):
            with tenant_atomic(self.context):
                Integration.objects.select_for_update(no_key=True).get(pk=self.integration.pk)
                worker = executor.submit(claim)
                self.assertTrue(worker_has_org_lock.wait(timeout=15))
                yield
            worker.result(timeout=30)

    def test_mirror_wins_concurrent_claim_and_hides_old_draft(self):
        self.configure_transport()
        self.set_ai(True)
        conversation, message, event = self.queue_reply()
        with patch("chatballs.api_connector.outbound._send_command") as send:
            with self.hold_connector_during_claim(event):
                result = self.send(self.observed())
                self.assertEqual(result.status_code, 202, getattr(result, "data", None))
            send.assert_not_called()

        self.assertEqual(NativeMirrorPublication.objects.get(message=message).status, PublicationStatus.SUPPRESSED)
        self.assertFalse(visible_messages(conversation.messages.all()).filter(pk=message.pk).exists())
        self.assertEqual(
            conversation.domain_events.filter(event_type="PUBLIC_REPLY", actor_kind="HUMAN").count(), 1,
        )
        self.assertFalse(conversation.domain_events.filter(event_type="PUBLIC_REPLY", actor_kind="AI").exists())
        self.assertEqual(self.send(self.echo(event.payload["command"]["command_id"])).status_code, 409)

    def test_claim_wins_and_timeout_retries_the_same_command_after_mirror(self):
        self.configure_transport()
        self.set_ai(True)
        _, message, event = self.queue_reply()

        def mirror_before_timeout(*args):
            self.assertFalse(connection.in_atomic_block)
            self.assertEqual(self.send(self.observed()).status_code, 202)
            raise RuntimeError("timeout")

        with patch("chatballs.api_connector.outbound._send_command", side_effect=mirror_before_timeout) as send:
            with self.assertRaisesRegex(RuntimeError, "timeout"):
                dispatch(event)
            first_command = send.call_args.args[2]
        self.assertEqual(NativeMirrorPublication.objects.get(message=message).status, PublicationStatus.CLAIMED)
        with patch("chatballs.api_connector.outbound._send_command") as send:
            dispatch(event)
            self.assertEqual(send.call_args.args[2], first_command)

    def test_disabling_ai_wins_concurrent_claim_and_hides_queued_ai(self):
        self.configure_transport()
        self.set_ai(True)
        conversation, message, event = self.queue_reply()
        with patch("chatballs.api_connector.outbound._send_command") as send:
            with self.hold_connector_during_claim(event):
                self.set_ai(False)
        send.assert_not_called()
        self.assertEqual(NativeMirrorPublication.objects.get(message=message).status, PublicationStatus.SUPPRESSED)
        self.assertFalse(visible_messages(conversation.messages.all()).filter(pk=message.pk).exists())

    def test_oversized_ai_answer_enters_operator_queue_and_sends_only_fallback(self):
        self.configure_transport()
        self.set_ai(True)
        conversation, _, event = self.queue_reply(text="😀" * 2001)
        conversation.refresh_from_db()
        self.assertEqual(conversation.control_mode, ControlMode.PAUSED)
        self.assertEqual(conversation.messages.get(author_type=MessageAuthor.CONTACT).ai_turn_state, AiTurnState.FAILED)
        self.assertNotIn("😀", event.payload["command"]["message"]["text"])
        with patch("chatballs.api_connector.outbound._send_command") as send:
            dispatch(event)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[2], event.payload["command"])

    def test_handoff_text_is_revoked_if_control_changes_after_its_own_pause(self):
        self.configure_transport()
        self.set_ai(True)
        conversation, message, event = self.queue_reply(text=f"I will ask an operator. {HANDOFF_TOKEN}")
        conversation.refresh_from_db()
        self.assertEqual(conversation.control_mode, ControlMode.PAUSED)
        self.assertEqual(event.payload["command"]["message"]["text"], "I will ask an operator.")
        Conversation.objects.filter(pk=conversation.pk).update(control_mode=ControlMode.AI)
        Conversation.objects.filter(pk=conversation.pk).update(control_mode=ControlMode.PAUSED)
        with patch("chatballs.api_connector.outbound._send_command") as send:
            dispatch(event)
        send.assert_not_called()
        self.assertEqual(NativeMirrorPublication.objects.get(message=message).status, PublicationStatus.SUPPRESSED)
