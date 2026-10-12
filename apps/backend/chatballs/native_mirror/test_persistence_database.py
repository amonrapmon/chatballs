"""Real PostgreSQL connection tests for dedup and tenant RLS."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from django.db import DatabaseError, close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase

from chatballs.channels.models import Channel
from chatballs.conversations.models import Conversation, ControlMode, Message
from chatballs.identity.bootstrap import bootstrap_owner
from chatballs.identity.models import HumanUser, Organization
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.native_mirror.classification import OriginClass
from chatballs.native_mirror.contracts import MirrorOutcome, NativeReplyEvent
from chatballs.native_mirror.models import NativeMirrorConversationState, NativeMirrorReceipt
from chatballs.native_mirror.service import accept_native_reply
from chatballs.tenancy.database import set_local_tenant
from chatballs.testing import system_tenant_context


class NativeMirrorDatabaseBoundaryTests(TransactionTestCase):
    def setUp(self):
        bootstrap_owner(email="mirror-concurrent@example.com", password="temporary-password")
        self.org = Organization.objects.get(slug="demo")
        self.user = HumanUser.objects.get(email="mirror-concurrent@example.com")
        self.context = system_tenant_context(self.org)
        channel = Channel.objects.create(
            organization=self.org, code="mirror-concurrent", name="Mirror concurrent"
        )
        self.integration = Integration.objects.create(
            organization=self.org, channel=channel,
            kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.GATEWAY,
            name="Gateway", secret="secret",
            config={"source_id": "tg-main", "native_mirror_mode": "ENABLED"},
        )
        contact = self.org.contacts.create(name="Guest")
        self.conversation = Conversation.objects.create(
            organization=self.org, channel=channel, contact=contact,
            connection=self.integration, external_chat_id="chat-1",
            control_mode=ControlMode.AI,
        )

    def event(self, **overrides):
        values = dict(
            integration_id=self.integration.id, provider=IntegrationProvider.GATEWAY,
            source_id="tg-main", external_chat_id="chat-1",
            event_id="event-1", external_message_id="provider-1",
            occurred_at=datetime(2026, 10, 12, tzinfo=UTC), text="Ответ",
        )
        values.update(overrides)
        return NativeReplyEvent(**values)

    def accept(self, event):
        return accept_native_reply(
            event=event, context=self.context,
            origin=OriginClass.EXTERNAL_AUTHORIZED, author_user_id=self.user.id,
        )

    def test_two_workers_accept_same_message_once(self):
        event = self.event()
        barrier = Barrier(3)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return self.accept(event).outcome
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            left = executor.submit(worker)
            right = executor.submit(worker)
            barrier.wait(timeout=15)
            results = (left.result(timeout=30), right.result(timeout=30))
        self.assertCountEqual(results, [MirrorOutcome.STORED, MirrorOutcome.DUPLICATE])
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(NativeMirrorReceipt.objects.count(), 1)
        self.assertEqual(NativeMirrorConversationState.objects.get().revision, 1)

    def test_parallel_distinct_messages_increment_revision_without_lost_update(self):
        barrier = Barrier(3)

        def worker(event):
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return self.accept(event).outcome
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(worker, self.event())
            second = executor.submit(worker, self.event(
                event_id="event-2", external_message_id="provider-2",
            ))
            barrier.wait(timeout=15)
            self.assertEqual(first.result(timeout=30), MirrorOutcome.STORED)
            self.assertEqual(second.result(timeout=30), MirrorOutcome.STORED)
        self.assertEqual(Message.objects.count(), 2)
        self.assertEqual(NativeMirrorConversationState.objects.get().revision, 2)

    def test_runtime_rls_does_not_read_other_organization_receipts(self):
        self.accept(self.event())
        other = Organization.objects.create(name="Other", slug="mirror-other")
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            self.assertEqual(NativeMirrorReceipt.objects.count(), 0)
            set_local_tenant(other.id)
            self.assertEqual(NativeMirrorReceipt.objects.count(), 0)
            self.assertEqual(NativeMirrorConversationState.objects.count(), 0)
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            set_local_tenant(self.org.id)
            self.assertEqual(NativeMirrorReceipt.objects.count(), 1)
            self.assertEqual(NativeMirrorConversationState.objects.count(), 1)

    def test_constraint_trigger_rejects_cross_tenant_receipt_reference(self):
        self.accept(self.event())
        other = Organization.objects.create(name="Other", slug="mirror-other-guard")
        receipt = NativeMirrorReceipt.objects.get()
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE native_mirror_nativemirrorreceipt "
                    "SET organization_id = %s WHERE id = %s",
                    [other.id, receipt.id],
                )
        receipt.refresh_from_db()
        self.assertEqual(receipt.organization_id, self.org.id)
