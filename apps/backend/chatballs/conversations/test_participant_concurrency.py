from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, transaction
from django.test import TransactionTestCase
from rest_framework.exceptions import ValidationError

from chatballs.conversations.participant_services import add_participant
from chatballs.conversations.participant_test_base import ParticipantTestBase
from chatballs.tenancy.database import tenant_atomic


class ParticipantConcurrencyTests(TransactionTestCase):
    def setUp(self):
        ParticipantTestBase.setUpTestData.__func__(type(self))
        self.organization.additional_participant_limit = 1
        self.organization.save(update_fields=["additional_participant_limit"])

    def concurrent_adds(self, targets):
        barrier = Barrier(2)

        def add(target):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                with tenant_atomic(self.context):
                    try:
                        row, created = add_participant(
                            context=self.context, conversation_id=self.conversation.pk,
                            membership_id=target, reason="Concurrent consultation",
                        )
                        return row.pk, created
                    except ValidationError:
                        return None, False
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(add, target) for target in targets]
            return [future.result(timeout=30) for future in futures]

    def test_concurrent_different_targets_cannot_exceed_limit(self):
        results = self.concurrent_adds([member.pk for member in self.members[1:]])
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(sum(pk is None for pk, _ in results), 1)
        self.assertEqual(self.conversation.participants.additional().count(), 1)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.members[0].user_id)

    def test_concurrent_duplicate_add_creates_one_participation(self):
        results = self.concurrent_adds([self.members[1].pk] * 2)
        self.assertEqual(results[0][0], results[1][0])
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(self.conversation.participants.count(), 1)

    def test_rollback_keeps_composition_and_journal_empty(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            add_participant(
                context=self.context, conversation_id=self.conversation.pk,
                membership_id=self.members[1].pk, reason="Rolled back",
            )
            raise RuntimeError("Abort operation")
        self.assertFalse(self.conversation.participants.exists())
