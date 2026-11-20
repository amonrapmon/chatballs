"""Prove that queued observations are serialized with edits and other workers."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase

from chatballs.api_connector.observed import ingest_observed_outgoing
from chatballs.api_connector.observed_test_fixture import ObservedOutgoingFixture
from chatballs.conversations.models import ConnectionIdentity, Contact, Conversation, Message
from chatballs.native_mirror.supersession import current_revision
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient


class ObservedOutgoingRaceTests(ObservedOutgoingFixture, TransactionTestCase):
    def worker(self, payload, ready=None):
        close_old_connections()
        try:
            if ready is not None:
                ready.wait(timeout=5)
            return TenantAPIClient().post(
                self.webhook, payload, format="json", HTTP_AUTHORIZATION=f"Bearer {self.token}",
            ).status_code
        finally:
            connection.close()

    def test_two_workers_with_same_provider_message_advance_one_revision(self):
        conversation = self.open_conversation()
        ready = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.worker, self.observed(), ready)
            second = pool.submit(self.worker, self.observed(event_id="another-event"), ready)
            self.assertEqual((first.result(timeout=8), second.result(timeout=8)), (202, 202))
        self.assertEqual(conversation.messages.filter(connector_origin="EXTERNAL_OBSERVED").count(), 1)
        self.assertEqual(current_revision(conversation_id=conversation.pk), 1)

    def test_two_outbound_first_messages_create_one_personal_route(self):
        ready = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.worker, self.observed(
                event_id="native-one", external_id="provider-one",
            ), ready)
            second = pool.submit(self.worker, self.observed(
                event_id="native-two", external_id="provider-two",
            ), ready)
            self.assertEqual(
                sorted((first.result(timeout=8), second.result(timeout=8))), [202, 202],
            )
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(ConnectionIdentity.objects.count(), 1)
        self.assertEqual(Message.objects.filter(connector_origin="EXTERNAL_OBSERVED").count(), 2)

    def test_cold_start_race_with_first_inbound_resolves_to_one_contact(self):
        incoming = self.incoming(event_id="guest-first", external_id="provider-inbound")
        incoming["sender"]["external_user_id"] = "chat-1"
        ready = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.worker, incoming, ready)
            second = pool.submit(self.worker, self.observed(
                event_id="native-first", external_id="provider-outbound",
            ), ready)
            self.assertEqual(
                sorted((first.result(timeout=8), second.result(timeout=8))), [202, 202],
            )
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Contact.objects.count(), 1)
        self.assertEqual(ConnectionIdentity.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 2)

    def test_inbound_and_observation_conflicting_ids_yield_a_typed_conflict(self):
        self.open_conversation()
        ready = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as pool:
            incoming = pool.submit(
                self.worker, self.incoming(event_id="shared", external_id="another-inbound"), ready,
            )
            observed = pool.submit(self.worker, self.observed(event_id="shared"), ready)
            results = sorted((incoming.result(timeout=8), observed.result(timeout=8)))
        self.assertEqual(results, [202, 409])

    def test_disable_commits_before_blocked_observation_applies(self):
        conversation = self.open_conversation()
        ready = Event()

        def signal_before_lock(*args, **kwargs):
            ready.set()
            return ingest_observed_outgoing(*args, **kwargs)

        with (
            ThreadPoolExecutor(max_workers=1) as pool,
            patch("chatballs.api_connector.dispatcher.ingest_observed_outgoing", side_effect=signal_before_lock),
        ):
            with tenant_atomic(self.organization.pk):
                self.assertEqual(self.set_mirror(False).status_code, 200)
                inflight = pool.submit(self.worker, self.observed())
                self.assertTrue(ready.wait(timeout=5))
            self.assertEqual(inflight.result(timeout=8), 202)
        self.assertFalse(conversation.messages.filter(connector_origin="EXTERNAL_OBSERVED").exists())
        self.assertEqual(current_revision(conversation_id=conversation.pk), 0)
