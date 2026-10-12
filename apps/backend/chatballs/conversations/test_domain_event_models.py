from datetime import timedelta
from uuid import uuid4

from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.domain_event_test_base import DomainEventTestBase
from chatballs.conversations.models import Conversation, Message, MessageAuthor


class DomainEventModelTests(DomainEventTestBase):
    def test_database_owns_time_and_per_conversation_sequence_even_for_bulk_insert(self):
        before = timezone.now()
        first = self.row(occurred_at=before - timedelta(days=90), sequence=900)
        first.save()
        first.refresh_from_db()
        second = self.row(event_type="PUBLIC_REPLY")
        second.save()
        self.assertEqual(second.sequence, 2)
        other = self.row(conversation_id=self.foreign_conversation.pk,
                         organization_id=self.foreign.pk, initiated_by_id=None,
                         responsible_id=None, group_id=None, connection_id=None, transport=None)
        other.save()
        self.assertEqual(other.sequence, 1)
        third = self.row(event_type="CLOSED")
        ConversationEvent.objects.bulk_create([third])
        self.assertEqual(third.sequence, 3)
        self.assertEqual(first.sequence, 1)
        self.assertLessEqual(before, first.occurred_at)
        self.assertLessEqual(first.occurred_at, second.occurred_at)
        self.assertLessEqual(second.occurred_at, third.occurred_at)
        self.assertLessEqual(third.occurred_at, timezone.now())

    def test_operation_deduplicates_each_fact_kind_without_losing_companion_facts(self):
        operation = uuid4()
        self.row(operation_id=operation).save()
        self.row(operation_id=operation, event_type="QUEUE_EXITED").save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.row(operation_id=operation).save()
        next_row = self.row()
        next_row.save()
        self.assertEqual(next_row.sequence, 3)
        self.assertEqual(ConversationEvent.objects.count(), 3)

    def test_domain_change_and_fact_rollback_together(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            Conversation.objects.filter(pk=self.conversation.pk).update(lifecycle="CLOSED")
            self.row(event_type="CLOSED").save()
            raise RuntimeError("Domain operation failed")
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.lifecycle, "OPEN")
        self.assertFalse(ConversationEvent.objects.exists())

    def test_snapshots_survive_reassignment_and_dimension_deletion(self):
        row = self.row()
        row.save()
        expected = (row.initiated_by_id, row.responsible_id, row.group_id,
                    row.connection_id, row.transport)
        Conversation.objects.filter(pk=self.conversation.pk).update(
            assigned_operator=None, group=None, connection=None
        )
        self.group.delete()
        self.member.delete()
        self.connection.delete()
        row.refresh_from_db()
        self.assertEqual((row.initiated_by_id, row.responsible_id, row.group_id,
                          row.connection_id, row.transport), expected)
        with self.assertRaises(DatabaseError), transaction.atomic():
            ConversationEvent.objects.filter(pk=row.pk).update(event_type="CLOSED")

    def test_delete_cascades_only_the_target_conversation_and_no_content_is_copied(self):
        row = self.row()
        row.save()
        Message.objects.create(conversation=self.conversation, author_type=MessageAuthor.CONTACT,
                               text="Private message", system_params={"private": "content"})
        allowed = {"id", "organization", "conversation", "event_type", "occurred_at", "sequence",
                   "operation_id", "actor_kind", "initiated_by_id", "responsible_id", "group_id",
                   "connection_id", "transport"}
        self.assertEqual({field.name for field in ConversationEvent._meta.fields}, allowed)
        self.conversation.delete()
        self.assertFalse(ConversationEvent.objects.filter(pk=row.pk).exists())
        self.assertTrue(Conversation.objects.filter(pk=self.foreign_conversation.pk).exists())

    def test_database_rejects_arbitrary_fact_codes_and_incomplete_transport(self):
        for changes in ({"event_type": "secret text"}, {"actor_kind": "UNKNOWN"},
                        {"transport": "CUSTOM"}, {"transport": None},
                        {"connection_id": None}):
            with self.subTest(changes=changes), self.assertRaises(DatabaseError), transaction.atomic():
                ConversationEvent.objects.bulk_create([self.row(**changes)])
