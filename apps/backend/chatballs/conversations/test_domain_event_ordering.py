from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from django.db import close_old_connections
from django.test import TransactionTestCase

from chatballs.channels.models import Channel
from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.models import Contact, Conversation
from chatballs.identity.models import Organization
from chatballs.tenancy.database import tenant_atomic


class DomainEventOrderingTests(TransactionTestCase):
    def test_concurrent_operations_get_distinct_ordered_sequences(self):
        organization = Organization.objects.create(name="Concurrent", slug="concurrent-facts")
        channel = Channel.objects.create(organization=organization, name="Facts", code="facts")
        contact = Contact.objects.create(organization=organization, name="Customer")
        conversation = Conversation.objects.create(
            organization=organization, channel=channel, contact=contact
        )
        barrier = Barrier(2)

        def insert():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                with tenant_atomic(organization.pk):
                    row = ConversationEvent.objects.create(
                        organization_id=organization.pk, conversation_id=conversation.pk,
                        event_type="QUEUE_ENTERED", actor_kind="SYSTEM", operation_id=uuid4(),
                    )
                    return row.sequence
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(insert) for _ in range(2)]
            self.assertEqual(sorted(future.result(timeout=20) for future in futures), [1, 2])
        events = list(ConversationEvent.objects.order_by("sequence"))
        self.assertEqual(len(events), 2)
        self.assertLessEqual(events[0].occurred_at, events[1].occurred_at)
