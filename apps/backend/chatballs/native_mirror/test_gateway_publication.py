"""Gateway AI publication claim and retry semantics without production transport."""

from unittest import mock

from django.test import TransactionTestCase

from chatballs.conversations.gateway_delivery import (
    GATEWAY_DELIVERY_COMMAND_REQUESTED,
    post_gateway_operator_message,
)
from chatballs.conversations.gateway_http import GatewayDeliveryError
from chatballs.conversations.models import (
    ControlMode, DeliveryStatus, Message, MessageAuthor,
)
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.identity.operation_modes import OperationMode
from chatballs.native_mirror.contracts import MirrorOutcome
from chatballs.native_mirror.models import NativeMirrorPublication, PublicationStatus
from chatballs.native_mirror.supersession_fixture import NativeMirrorTurnFixture


class GatewayPublicationTests(NativeMirrorTurnFixture, TransactionTestCase):
    def _publish(self):
        turn = self._start()
        self.assertEqual(self._finish(turn, "Ответ AI"), "Ответ AI")
        message = Message.objects.get(author_type=MessageAuthor.AI)
        event = OutboxEvent.objects.get(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
            aggregate_id=str(message.id),
        )
        return message, event

    def _send(self, event):
        with mock.patch(
            "chatballs.conversations.gateway_event_handlers.send_delivery_command",
        ) as send:
            dispatch(event)
            return send.call_args_list

    def test_new_ai_response_is_queued_with_snapshot_before_dispatch(self):
        message, event = self._publish()
        pub = NativeMirrorPublication.objects.get(message=message)
        self.assertEqual(pub.revision, 0)
        self.assertEqual(pub.status, PublicationStatus.QUEUED)
        self.assertIsNone(pub.claimed_at)
        self.assertEqual(event.payload["command"]["command_id"], str(message.gateway_command_id))

    def test_native_reply_before_claim_suppresses_network_dispatch(self):
        message, event = self._publish()
        self.assertEqual(self._mirror().outcome, MirrorOutcome.STORED)
        self.assertEqual(self._send(event), [])
        pub = NativeMirrorPublication.objects.get(message=message)
        self.assertEqual(pub.status, PublicationStatus.SUPPRESSED)
        self.assertIsNotNone(pub.suppressed_at)
        self.assertIsNone(pub.claimed_at)
        self.assertEqual(self._send(event), [])
        pub.refresh_from_db()
        self.assertEqual(pub.status, PublicationStatus.SUPPRESSED)

    def test_claim_before_mirror_permits_retries_with_same_command_id(self):
        message, event = self._publish()
        first = self._send(event)
        self.assertEqual(len(first), 1)
        self.assertEqual(
            NativeMirrorPublication.objects.get(message=message).status,
            PublicationStatus.CLAIMED,
        )
        self.assertEqual(self._mirror().outcome, MirrorOutcome.STORED)
        self.organization.operation_mode = OperationMode.OPERATORS_ONLY
        self.organization.operation_mode_version += 1
        self.organization.save(update_fields=["operation_mode", "operation_mode_version"])
        self.conversation.control_mode = ControlMode.HUMAN
        self.conversation.assigned_operator = self.owner
        self.conversation.save(update_fields=["control_mode", "assigned_operator"])
        second = self._send(event)
        self.assertEqual(len(second), 1)
        first_command = first[0].kwargs["command"]
        second_command = second[0].kwargs["command"]
        self.assertEqual(first_command["command_id"], second_command["command_id"])
        self.assertEqual(first_command["command_id"], str(message.gateway_command_id))
        self.assertEqual(
            NativeMirrorPublication.objects.get(message=message).status,
            PublicationStatus.CLAIMED,
        )

    def test_http_timeout_after_claim_still_allows_safe_idempotent_retry(self):
        message, event = self._publish()
        with (
            mock.patch(
                "chatballs.conversations.gateway_event_handlers.send_delivery_command",
                side_effect=GatewayDeliveryError("network timeout"),
            ) as send,
            self.assertRaises(GatewayDeliveryError),
        ):
            dispatch(event)
        self.assertEqual(send.call_count, 1)
        pub = NativeMirrorPublication.objects.get(message=message)
        self.assertEqual(pub.status, PublicationStatus.CLAIMED)
        first_claim_time = pub.claimed_at
        self._mirror()
        retried = self._send(event)
        self.assertEqual(len(retried), 1)
        pub.refresh_from_db()
        self.assertEqual(pub.claimed_at, first_claim_time)

    def test_legacy_ai_without_publication_row_is_checked_and_claimed(self):
        self.integration.config = {
            "source_id": "tg-native", "base_url": "https://gateway.example.test/",
        }
        self.integration.save(update_fields=["config"])
        message, event = self._publish()
        self.assertFalse(NativeMirrorPublication.objects.filter(message=message).exists())
        self.assertEqual(len(self._send(event)), 1)
        self.assertEqual(
            NativeMirrorPublication.objects.get(message=message).status,
            PublicationStatus.CLAIMED,
        )

    def test_legacy_ai_first_claim_remains_retryable_after_takeover(self):
        self.integration.config = {
            "source_id": "tg-native", "base_url": "https://gateway.example.test/",
        }
        self.integration.save(update_fields=["config"])
        message, event = self._publish()
        self.assertFalse(NativeMirrorPublication.objects.filter(message=message).exists())
        self.assertEqual(len(self._send(event)), 1)

        self.organization.operation_mode = OperationMode.OPERATORS_ONLY
        self.organization.operation_mode_version += 1
        self.organization.save(update_fields=["operation_mode", "operation_mode_version"])
        self.conversation.control_mode = ControlMode.HUMAN
        self.conversation.assigned_operator = self.owner
        self.conversation.save(update_fields=["control_mode", "assigned_operator"])

        self.assertEqual(len(self._send(event)), 1)
        self.assertEqual(
            NativeMirrorPublication.objects.get(message=message).status,
            PublicationStatus.CLAIMED,
        )

    def test_legacy_ai_without_publication_is_suppressed_after_operator_takeover(self):
        self.integration.config = {
            "source_id": "tg-native", "base_url": "https://gateway.example.test/",
        }
        self.integration.save(update_fields=["config"])
        message, event = self._publish()
        self.assertFalse(NativeMirrorPublication.objects.filter(message=message).exists())
        self.conversation.control_mode = ControlMode.HUMAN
        self.conversation.assigned_operator = self.owner
        self.conversation.save(update_fields=["control_mode", "assigned_operator"])

        self.assertEqual(self._send(event), [])
        message.refresh_from_db()
        self.assertEqual(message.delivery_status, DeliveryStatus.SUPPRESSED)

    def test_legacy_ai_without_publication_is_suppressed_after_native_revision_changes(self):
        self.integration.config = {
            "source_id": "tg-native", "base_url": "https://gateway.example.test/",
        }
        self.integration.save(update_fields=["config"])
        message, event = self._publish()
        self.assertFalse(NativeMirrorPublication.objects.filter(message=message).exists())
        self.integration.config["native_mirror_mode"] = "ENABLED"
        self.integration.save(update_fields=["config"])
        self.assertEqual(self._mirror().outcome, MirrorOutcome.STORED)

        self.assertEqual(self._send(event), [])
        message.refresh_from_db()
        self.assertEqual(message.delivery_status, DeliveryStatus.SUPPRESSED)

    def test_legacy_ai_without_publication_is_suppressed_in_operators_only(self):
        self.integration.config = {
            "source_id": "tg-native", "base_url": "https://gateway.example.test/",
        }
        self.integration.save(update_fields=["config"])
        message, event = self._publish()
        self.organization.operation_mode = OperationMode.OPERATORS_ONLY
        self.organization.operation_mode_version += 1
        self.organization.save(update_fields=["operation_mode", "operation_mode_version"])

        self.assertFalse(NativeMirrorPublication.objects.filter(message=message).exists())
        self.assertEqual(self._send(event), [])
        message.refresh_from_db()
        self.assertEqual(message.delivery_status, DeliveryStatus.SUPPRESSED)

    def test_legacy_ai_without_publication_respects_cancelled_delivery(self):
        self.integration.config = {
            "source_id": "tg-native", "base_url": "https://gateway.example.test/",
        }
        self.integration.save(update_fields=["config"])
        message, event = self._publish()
        message.ai_delivery = {**message.ai_delivery, "cancelled": True}
        message.save(update_fields=["ai_delivery"])

        self.assertFalse(NativeMirrorPublication.objects.filter(message=message).exists())
        self.assertEqual(self._send(event), [])
        message.refresh_from_db()
        self.assertEqual(message.delivery_status, DeliveryStatus.SUPPRESSED)

    def test_queued_ai_is_suppressed_when_organization_becomes_operators_only(self):
        message, event = self._publish()
        self.organization.operation_mode = OperationMode.OPERATORS_ONLY
        self.organization.operation_mode_version += 1
        self.organization.save(update_fields=["operation_mode", "operation_mode_version"])

        self.assertEqual(self._send(event), [])
        self.assertEqual(
            NativeMirrorPublication.objects.get(message=message).status,
            PublicationStatus.SUPPRESSED,
        )

    def test_queued_ai_is_suppressed_when_operation_mode_version_changes(self):
        message, event = self._publish()
        self.organization.operation_mode_version += 1
        self.organization.save(update_fields=["operation_mode_version"])

        self.assertEqual(self._send(event), [])
        self.assertEqual(
            NativeMirrorPublication.objects.get(message=message).status,
            PublicationStatus.SUPPRESSED,
        )

    def test_queued_ai_is_suppressed_when_delivery_was_cancelled(self):
        message, event = self._publish()
        message.ai_delivery = {**message.ai_delivery, "cancelled": True}
        message.save(update_fields=["ai_delivery"])

        self.assertEqual(self._send(event), [])
        self.assertEqual(
            NativeMirrorPublication.objects.get(message=message).status,
            PublicationStatus.SUPPRESSED,
        )
        message.refresh_from_db()
        self.assertEqual(message.delivery_status, DeliveryStatus.SUPPRESSED)

    def test_operator_delivery_never_gets_ai_publication_claim(self):
        self._mirror()
        self.organization.operation_mode = OperationMode.OPERATORS_ONLY
        self.organization.operation_mode_version += 1
        self.organization.save(update_fields=["operation_mode", "operation_mode_version"])
        from chatballs.tenancy.database import tenant_atomic

        with tenant_atomic(self.context):
            operator_reply = post_gateway_operator_message(
                context=self.context, conversation=self.conversation,
                text="Ответ Chatballs оператора",
            )
        self.assertEqual(operator_reply.author_type, MessageAuthor.OPERATOR)
        self.assertFalse(NativeMirrorPublication.objects.filter(message=operator_reply).exists())
        event = OutboxEvent.objects.get(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
            aggregate_id=str(operator_reply.id),
        )
        self.assertEqual(len(self._send(event)), 1)

    def test_publication_queue_failure_rolls_back_ai_message_and_outbox(self):
        turn = self._start()
        with (
            mock.patch(
                "chatballs.native_mirror.publication.NativeMirrorPublication.objects.create",
                side_effect=RuntimeError("publication unavailable"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self._finish(turn)
        self.assertFalse(Message.objects.filter(author_type=MessageAuthor.AI).exists())
        self.assertFalse(OutboxEvent.objects.filter(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
        ).exists())
        self.assertFalse(NativeMirrorPublication.objects.exists())

    def test_mismatched_recipient_is_never_sent_for_a_guarded_ai_reply(self):
        _message, event = self._publish()
        event.payload["command"]["recipient"]["external_chat_id"] = "wrong-chat"
        with mock.patch(
            "chatballs.conversations.gateway_event_handlers.send_delivery_command",
        ) as send, self.assertRaises(ValueError):
            dispatch(event)
        send.assert_not_called()
        self.assertEqual(
            NativeMirrorPublication.objects.get().status, PublicationStatus.QUEUED,
        )

    def test_provider_gateway_metadata_is_preserved_on_suppression(self):
        message, event = self._publish()
        original_command_id = message.gateway_command_id
        self._mirror()
        self.assertEqual(self._send(event), [])
        message.refresh_from_db()
        self.assertEqual(message.gateway_command_id, original_command_id)
        self.assertEqual(message.delivery_status, "suppressed")
        self.assertIsNotNone(message.delivery_status_at)
