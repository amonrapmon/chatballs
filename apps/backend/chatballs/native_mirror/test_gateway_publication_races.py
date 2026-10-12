"""PostgreSQL serialization tests for native reply vs Gateway dispatch claim."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import DatabaseError, close_old_connections, connection, connections, transaction
from django.test import TransactionTestCase

from chatballs.conversations.gateway_delivery import GATEWAY_DELIVERY_COMMAND_REQUESTED
from chatballs.conversations.models import Message, MessageAuthor
from chatballs.events.models import OutboxEvent
from chatballs.identity.models import Organization
from chatballs.native_mirror.contracts import MirrorOutcome
from chatballs.native_mirror.models import NativeMirrorPublication, PublicationStatus
from chatballs.native_mirror.publication import claim_ai_publication
from chatballs.native_mirror.supersession_fixture import NativeMirrorTurnFixture
from chatballs.tenancy.database import set_local_tenant, tenant_atomic


class GatewayPublicationRaceTests(NativeMirrorTurnFixture, TransactionTestCase):
    def _queued(self):
        turn = self._start()
        self._finish(turn, "Ответ AI")
        message = Message.objects.get(author_type=MessageAuthor.AI)
        return OutboxEvent.objects.get(
            event_type=GATEWAY_DELIVERY_COMMAND_REQUESTED,
            aggregate_id=str(message.id),
        ).payload["command"]

    def _claim(self, command):
        with tenant_atomic(self.context):
            return claim_ai_publication(
                context=self.context, integration_id=self.integration.id,
                command=command,
            )

    def test_mirror_transaction_first_suppresses_remote_dispatch_claim(self):
        command = self._queued()
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=15)
                return self._claim(command)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with tenant_atomic(self.context):
                self.conversation.__class__.objects.select_for_update().get(
                    id=self.conversation.id,
                )
                future = executor.submit(worker)
                barrier.wait(timeout=15)
                self.assertEqual(self._mirror().outcome, MirrorOutcome.STORED)
            self.assertFalse(future.result(timeout=30))

        self.assertEqual(
            NativeMirrorPublication.objects.get().status,
            PublicationStatus.SUPPRESSED,
        )

    def test_dispatch_claim_first_keeps_network_boundary_irrevocable(self):
        command = self._queued()
        self.assertTrue(self._claim(command))
        self.assertEqual(self._mirror().outcome, MirrorOutcome.STORED)
        self.assertTrue(self._claim(command))
        publication = NativeMirrorPublication.objects.get()
        self.assertEqual(publication.status, PublicationStatus.CLAIMED)
        self.assertIsNotNone(publication.claimed_at)
        self.assertIsNone(publication.suppressed_at)

    def test_publication_rls_is_tenant_scoped_and_fail_closed(self):
        self._queued()
        other = Organization.objects.create(name="Other", slug="mirror-other-publication")
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            self.assertEqual(NativeMirrorPublication.objects.count(), 0)
            set_local_tenant(other.id)
            self.assertEqual(NativeMirrorPublication.objects.count(), 0)
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            set_local_tenant(self.organization.id)
            self.assertEqual(NativeMirrorPublication.objects.count(), 1)

    def test_publication_cross_tenant_message_reference_rejected(self):
        self._queued()
        other = Organization.objects.create(name="Other", slug="mirror-other-pub-fk")
        row = NativeMirrorPublication.objects.get()
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE native_mirror_nativemirrorpublication "
                    "SET organization_id = %s WHERE id = %s",
                    [other.id, row.id],
                )
        row.refresh_from_db()
        self.assertEqual(row.organization_id, self.organization.id)
