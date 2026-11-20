"""Provider-observed outgoing text must not masquerade as inbound or Chatballs send."""
from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

from django.test import TestCase

from chatballs.api_connector.observed_test_fixture import ObservedOutgoingFixture
from chatballs.api_connector.outbound import CONNECTOR_OUTBOUND_REQUESTED
from chatballs.conversations.models import (
    AiTurnState,
    ConnectionIdentity,
    Contact,
    Conversation,
    ControlMode,
    ExpectedResponder,
    Message,
    LifecycleState,
    MessageAuthor,
)
from chatballs.events.models import InboxEvent, OutboxEvent
from chatballs.identity.models import AuditEvent
from chatballs.integrations.models import IntegrationProvider
from chatballs.integrations.services import IntegrationInput, create_integration
from chatballs.native_mirror.supersession import current_revision
from chatballs.testing import system_tenant_context


class APIConnectorObservedOutgoingTests(ObservedOutgoingFixture, TestCase):
    def test_observed_reply_appears_in_native_history_without_new_outbox(self):
        conversation = self.open_conversation()
        before = OutboxEvent.objects.count()
        result = self.send(self.observed())
        self.assertEqual(result.status_code, 202, result.data)
        self.assertEqual(result.data, {"accepted": True, "id": "observed-1"})
        messages = list(Message.objects.filter(conversation=conversation).order_by("pk"))
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].author_type, MessageAuthor.CONTACT)
        reply = messages[1]
        self.assertEqual(reply.author_type, MessageAuthor.OPERATOR)
        self.assertIsNone(reply.author_user_id)
        self.assertEqual(reply.external_id, "native-operator-1")
        self.assertEqual(reply.external_occurred_at, self.occurred_at)
        self.assertEqual(reply.connector_origin, "EXTERNAL_OBSERVED")
        self.assertEqual(OutboxEvent.objects.count(), before)
        history = self.client.get(f"/api/v1/conversations/{conversation.pk}/messages/")
        self.assertEqual(history.status_code, 200)
        found = next(m for m in history.data["items"] if m["id"] == reply.pk)
        self.assertEqual(found["connectorOrigin"], "EXTERNAL_OBSERVED")
        self.assertIsNone(found["authorUserId"])
        self.assertFalse(found.get("connectorDelivery"))

    def test_outbound_first_creates_native_contact_and_operator_history(self):
        self.assertEqual(Contact.objects.count(), 0)
        event = self.observed()
        result = self.send(event)
        self.assertEqual(result.status_code, 202, result.data)
        conversation = Conversation.objects.get(connection=self.integration, external_chat_id="chat-1")
        identity = ConnectionIdentity.objects.get(
            connection=self.integration, external_user_id="chat-1",
        )
        self.assertEqual(conversation.contact_id, identity.contact_id)
        self.assertEqual(identity.contact.name, "")
        self.assertNotEqual(identity.external_user_id, event["sender"]["external_user_id"])
        self.assertEqual(conversation.route_external_user_id, "chat-1")
        self.assertEqual(conversation.control_mode, ControlMode.HUMAN)
        self.assertEqual(conversation.expected_responder, ExpectedResponder.CUSTOMER)
        self.assertIsNone(conversation.assigned_operator_id)
        self.assertIsNone(conversation.waiting_since)
        self.assertEqual(conversation.group_id, self.integration.channel.group_id)
        self.assertEqual(conversation.messages.count(), 1)
        message = conversation.messages.get()
        self.assertEqual(message.author_type, MessageAuthor.OPERATOR)
        self.assertIsNone(message.author_user_id)
        self.assertEqual(message.connector_origin, "EXTERNAL_OBSERVED")
        self.assertEqual(message.external_id, "native-operator-1")
        self.assertFalse(OutboxEvent.objects.filter(event_type=CONNECTOR_OUTBOUND_REQUESTED).exists())
        self.assertEqual(conversation.last_message_at, conversation.last_activity_at)
        self.assertEqual(self.send(event).status_code, 202)
        self.assertEqual(self.send(self.observed(event_id="second-event")).status_code, 202)
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(ConnectionIdentity.objects.count(), 1)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(InboxEvent.objects.filter(
            source=f"api_connector:{self.integration.pk}", external_event_id="observed-1",
        ).count(), 1)

    def test_outbound_first_reuses_existing_identity_without_creating_contact(self):
        contact = Contact.objects.create(
            organization=self.organization, name="Знакомый контакт",
        )
        ConnectionIdentity.objects.create(
            contact=contact, connection=self.integration, external_user_id="chat-1",
        )
        self.assertEqual(self.send(self.observed()).status_code, 202)
        created = Conversation.objects.get(connection=self.integration)
        self.assertEqual(created.contact_id, contact.pk)
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(ConnectionIdentity.objects.count(), 1)

    def test_outbound_first_accepts_guest_reply_in_the_same_route(self):
        self.assertEqual(self.send(self.observed()).status_code, 202)
        incoming = self.incoming(event_id="guest-reply", external_id="guest-reply-message")
        # For a personal GREEN-API chat, the provider's external chat ID
        # identifies the peer. The incoming sender therefore matches it.
        incoming["sender"]["external_user_id"] = "chat-1"
        self.assertEqual(self.send(incoming).status_code, 202)
        conversation = Conversation.objects.get(connection=self.integration)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(conversation.messages.count(), 2)
        self.assertEqual(conversation.messages.filter(
            author_type=MessageAuthor.CONTACT,
        ).count(), 1)
        self.assertEqual(conversation.control_mode, ControlMode.HUMAN)

    def test_outbound_first_does_not_create_dialog_when_mirroring_disabled(self):
        self.assertEqual(self.set_mirror(False).status_code, 200)
        self.assertEqual(self.send(self.observed()).status_code, 202)
        self.assertFalse(Conversation.objects.exists())
        self.assertFalse(Contact.objects.exists())
        self.assertFalse(ConnectionIdentity.objects.exists())
        self.assertFalse(Message.objects.exists())

    def test_outbound_first_does_not_replay_pre_cutover_messages(self):
        old = self.observed()
        old["event"]["occurred_at"] = (
            self.cutover - timedelta(minutes=1)
        ).isoformat().replace("+00:00", "Z")
        self.assertEqual(self.send(old).status_code, 202)
        self.assertFalse(Conversation.objects.exists())
        self.assertFalse(Contact.objects.exists())

    def test_outbound_first_both_telegram_and_max_connector_services(self):
        for service in ("tg_green_api", "max_green_api"):
            with self.subTest(service=service):
                integration = create_integration(
                    context=system_tenant_context(self.organization),
                    data=IntegrationInput(
                        provider=IntegrationProvider.API_CONNECTOR,
                        name=f"Adapter {service}", config={"connectorService": service},
                    ),
                )
                credential = self.client.post(
                    f"/api/v1/integrations/{integration.pk}/connector-credential/",
                    data={}, format="json",
                ).data
                self.assertEqual(
                    self.set_mirror(True, connection_id=integration.pk).status_code, 200,
                )
                observed = deepcopy(self.observed(
                    event_id=f"first-{service}", external_id=f"out-{service}",
                    chat_id="shared-peer-id",
                ))
                observed["source_id"] = credential["sourceId"]
                response = self.send(
                    observed, url=credential["webhookPath"], token=credential["token"],
                )
                self.assertEqual(response.status_code, 202, response.data)
                chat = Conversation.objects.get(
                    connection=integration, external_chat_id="shared-peer-id",
                )
                self.assertEqual(chat.messages.count(), 1)
                self.assertEqual(chat.route_external_user_id, "shared-peer-id")
                self.assertEqual(chat.messages.get().connector_origin, "EXTERNAL_OBSERVED")

    def test_outbound_first_reopens_closed_route_without_reusing_old_history(self):
        self.assertEqual(self.send(self.observed()).status_code, 202)
        prior = Conversation.objects.get(connection=self.integration)
        prior.lifecycle = LifecycleState.CLOSED
        prior.save(update_fields=["lifecycle"])
        self.assertEqual(self.send(self.observed(
            event_id="next-mirror", external_id="native-operator-2",
        )).status_code, 202)
        reopened = Conversation.objects.get(
            connection=self.integration, lifecycle=LifecycleState.OPEN,
        )
        self.assertNotEqual(reopened.pk, prior.pk)
        self.assertEqual(reopened.previous_conversation_id, prior.pk)
        self.assertEqual(reopened.contact_id, prior.contact_id)
        self.assertEqual(reopened.route_external_user_id, prior.route_external_user_id)
        self.assertEqual(reopened.messages.count(), 1)
        self.assertEqual(prior.messages.count(), 1)

    def test_outbound_first_stays_scoped_to_its_connection(self):
        second = create_integration(
            context=system_tenant_context(self.organization),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR, name="Second connector",
                config={"connectorService": "custom_adapter"},
            ),
        )
        credential = self.client.post(
            f"/api/v1/integrations/{second.pk}/connector-credential/",
            data={}, format="json",
        ).data
        self.assertEqual(self.set_mirror(True, connection_id=second.pk).status_code, 200)
        first = self.observed()
        second_event = deepcopy(first)
        second_event["source_id"] = credential["sourceId"]
        self.assertEqual(self.send(first).status_code, 202)
        self.assertEqual(self.send(
            second_event, token=credential["token"], url=credential["webhookPath"],
        ).status_code, 202)
        self.assertEqual(Conversation.objects.count(), 2)
        self.assertEqual(Contact.objects.count(), 2)
        self.assertEqual(ConnectionIdentity.objects.count(), 2)
        self.assertNotEqual(
            Conversation.objects.get(connection=self.integration).contact_id,
            Conversation.objects.get(connection=second).contact_id,
        )

    def test_replay_and_duplicate_provider_id_are_idempotent(self):
        conversation = self.open_conversation()
        event = self.observed()
        self.assertEqual(self.send(event).status_code, 202)
        self.assertEqual(self.send(event).status_code, 202)
        duplicate_new_event = deepcopy(event)
        duplicate_new_event["event"]["id"] = "observed-2"
        self.assertEqual(self.send(duplicate_new_event).status_code, 202)
        self.assertEqual(Message.objects.filter(conversation=conversation).count(), 2)
        self.assertEqual(
            InboxEvent.objects.filter(
                source=f"api_connector:{self.integration.pk}",
                external_event_id__startswith="observed-",
            ).count(),
            2,
        )
        changed = deepcopy(event)
        changed["message"]["text"] = "Изменено"
        conflict = self.send(changed)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["error"], "id_conflict")

    def test_provider_message_with_a_different_quote_conflicts(self):
        conversation = self.open_conversation()
        event = self.observed()
        self.assertEqual(self.send(event).status_code, 202)
        event["event"]["id"] = "distinct-event"
        event["message"]["reply_to_external_message_id"] = "guest-message-1"
        conflict = self.send(event)
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data["error"], "external_message_id_conflict")
        self.assertEqual(conversation.messages.filter(connector_origin="EXTERNAL_OBSERVED").count(), 1)

    def test_observed_cannot_reuse_an_inbound_event_id(self):
        self.open_conversation()
        candidate = self.observed(event_id="in-1")
        response = self.send(candidate)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"], "id_conflict")
        self.assertFalse(Message.objects.filter(connector_origin="EXTERNAL_OBSERVED").exists())

    def test_same_event_id_with_new_provider_identity_is_conflict(self):
        self.open_conversation()
        event = self.observed()
        self.assertEqual(self.send(event).status_code, 202)
        changed = deepcopy(event)
        changed["message"]["external_message_id"] = "native-operator-2"
        self.assertEqual(self.send(changed).status_code, 409)
        self.assertEqual(
            Message.objects.filter(connector_origin="EXTERNAL_OBSERVED").count(), 1,
        )

    def test_new_revision_supersedes_ai_without_pausing_and_replay_leaves_new_turn(self):
        conversation = self.open_conversation()
        conversation.control_mode = ControlMode.AI
        conversation.expected_responder = ExpectedResponder.AI
        conversation.waiting_since = None
        conversation.save(update_fields=["control_mode", "expected_responder", "waiting_since"])
        old_turn = conversation.messages.get(author_type=MessageAuthor.CONTACT)
        old_turn.ai_turn_state = AiTurnState.RUNNING
        old_turn.save(update_fields=["ai_turn_state"])
        outbox_before = OutboxEvent.objects.count()
        event = self.observed()
        event["message"]["reply_to_external_message_id"] = old_turn.external_id
        self.assertEqual(self.send(event).status_code, 202)
        conversation.refresh_from_db()
        old_turn.refresh_from_db()
        self.assertEqual(old_turn.ai_turn_state, AiTurnState.DONE)
        self.assertEqual(current_revision(conversation_id=conversation.pk), 1)
        self.assertEqual(conversation.control_mode, ControlMode.AI)
        self.assertIsNone(conversation.assigned_operator_id)
        self.assertEqual(OutboxEvent.objects.count(), outbox_before)
        reply = conversation.messages.get(connector_origin="EXTERNAL_OBSERVED")
        self.assertEqual(reply.external_reply_to_id, old_turn.external_id)

        new_turn = conversation.messages.create(author_type=MessageAuthor.CONTACT, ai_turn_state=AiTurnState.RUNNING)
        self.assertEqual(self.send(event).status_code, 202)
        event["event"]["id"] = "provider-duplicate"
        self.assertEqual(self.send(event).status_code, 202)
        new_turn.refresh_from_db()
        self.assertEqual(new_turn.ai_turn_state, AiTurnState.RUNNING)
        self.assertEqual(current_revision(conversation_id=conversation.pk), 1)

    def test_disabled_and_reenabled_do_not_import_queued_events(self):
        conversation = self.open_conversation()
        event = self.observed()
        result = self.set_mirror(False)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertIs(result.data["integration"]["config"]["mirrorExternalOutgoingEnabled"], False)
        skipped = self.send(event)
        self.assertEqual(skipped.status_code, 202)
        self.assertEqual(skipped.data, {"accepted": True, "id": "observed-1"})
        self.assertEqual(current_revision(conversation_id=conversation.pk), 0)

        self.assertEqual(self.set_mirror(True, at=self.cutover + timedelta(seconds=50)).status_code, 200)
        self.assertEqual(self.send(event).status_code, 202)
        self.assertEqual(self.send(self.observed(event_id="not-attempted")).status_code, 202)
        self.assertEqual(conversation.messages.count(), 1)

        self.occurred_at += timedelta(seconds=40)
        self.observed_at += timedelta(seconds=40)
        self.assertEqual(self.send(self.observed(event_id="in-current-period")).status_code, 202)
        self.assertEqual(conversation.messages.count(), 2)
        self.assertEqual(current_revision(conversation_id=conversation.pk), 1)

    def test_legacy_envelope_without_first_seen_is_acknowledged_without_mirroring(self):
        conversation = self.open_conversation()
        event = self.observed()
        del event["event"]["observed_at"]
        self.assertEqual(self.send(event).status_code, 202)
        self.assertEqual(conversation.messages.count(), 1)

    def test_mirror_config_is_strictly_boolean_and_audited(self):
        response = self.set_mirror("true")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.set_mirror(False).status_code, 200)
        events = AuditEvent.objects.filter(
            object_id=str(self.integration.pk), action="integrations.integration_updated",
        ).order_by("pk")
        self.assertEqual(
            [event.payload["mirrorExternalOutgoingEnabled"] for event in events],
            [{"previous": False, "current": True}, {"previous": True, "current": False}],
        )

    def test_human_assignment_remains_and_customer_is_expected(self):
        conversation = self.open_conversation()
        conversation.control_mode = ControlMode.HUMAN
        conversation.assigned_operator = self.owner
        conversation.waiting_since = None
        conversation.save(update_fields=["control_mode", "assigned_operator", "waiting_since"])
        self.assertEqual(self.send(self.observed()).status_code, 202)
        conversation.refresh_from_db()
        self.assertEqual(conversation.control_mode, ControlMode.HUMAN)
        self.assertEqual(conversation.assigned_operator_id, self.owner.pk)
        self.assertEqual(conversation.expected_responder, ExpectedResponder.CUSTOMER)
        self.assertIsNone(Message.objects.get(connector_origin="EXTERNAL_OBSERVED").author_user_id)

    def test_wrong_route_and_connection_cannot_add_an_observed_message(self):
        self.open_conversation()
        observed = self.observed()
        self.assertEqual(self.send(observed, token="wrong-token").status_code, 401)
        wrong_source = deepcopy(observed)
        wrong_source["source_id"] = "connection-99999"
        self.assertEqual(self.send(wrong_source).status_code, 409)
        # A different *authenticated* personal route is now a valid
        # outbound-first conversation, never a mutation of the original.
        self.assertEqual(self.send(self.observed(chat_id="not-our-chat")).status_code, 202)
        self.assertEqual(Conversation.objects.filter(connection=self.integration).count(), 2)
        second = create_integration(
            context=system_tenant_context(self.organization),
            data=IntegrationInput(
                provider=IntegrationProvider.API_CONNECTOR, name="Other adapter",
                config={"connectorService": "custom_adapter"},
            ),
        )
        self.assertEqual(self.set_mirror(True, connection_id=second.pk).status_code, 200)
        credential = self.client.post(
            f"/api/v1/integrations/{second.pk}/connector-credential/",
            data={}, format="json",
        ).data
        foreign = deepcopy(observed)
        foreign["source_id"] = credential["sourceId"]
        result = self.send(foreign, token=credential["token"], url=credential["webhookPath"])
        self.assertEqual(result.status_code, 202)
        self.assertEqual(
            Message.objects.filter(conversation__connection=second, connector_origin="EXTERNAL_OBSERVED").count(), 1,
        )
        self.assertEqual(
            Message.objects.filter(conversation__connection=self.integration, connector_origin="EXTERNAL_OBSERVED").count(), 1,
        )

    def test_contact_id_collision_cannot_overwrite_inbound(self):
        self.open_conversation()
        bad = self.send(self.observed(external_id="guest-message-1"))
        self.assertEqual(bad.status_code, 409)
        self.assertEqual(bad.data["error"], "external_message_id_conflict")
        self.assertFalse(Message.objects.filter(connector_origin="EXTERNAL_OBSERVED").exists())

    def test_malformed_and_unsupported_variants_fail_closed(self):
        self.open_conversation()
        good = self.observed()
        cases = [
            ({**good, "sender": {"external_user_id": "u", "author_user_id": 1}}, 400),
            ({**good, "message": {**good["message"], "actor": "contact"}}, 422),
            ({**good, "message": {**good["message"], "direction": "inbound"}}, 422),
            ({**good, "message": {**good["message"], "attachments": [{"x": 1}]}}, 422),
            ({**good, "message": {**good["message"], "html": "<b>hello</b>"}}, 422),
            ({**good, "message": {**good["message"], "kind": "file"}}, 422),
            ({**good, "message": {**good["message"], "text": ""}}, 400),
            ({**good, "conversation": {"external_chat_id": "chat-1", "thread": {"id": "1"}}}, 422),
        ]
        for payload, status in cases:
            with self.subTest(payload=payload):
                self.assertEqual(self.send(payload).status_code, status)
        self.assertFalse(Message.objects.filter(connector_origin="EXTERNAL_OBSERVED").exists())
