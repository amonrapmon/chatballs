from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from django.db import connection, connections
from django.test import TransactionTestCase

from chatballs.conversations.assignment import assign_operator
from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.models import Conversation
from chatballs.conversations.transfer_models import ConversationTransfer
from chatballs.conversations.transfer_test_base import TransferTestBase
from chatballs.conversations.transfer_transition import AssignmentConflict
from chatballs.events.models import OutboxEvent
from chatballs.identity.models import EmployeeRole
from chatballs.notifications.models import Notification
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


class TransferConcurrencyTests(TransactionTestCase):
    def setUp(self):
        TransferTestBase.setUpTestData.__func__(type(self))
        self.context = TenantContext.for_membership(self.members[EmployeeRole.OWNER])

    def run_concurrently(self, requests):
        barrier = Barrier(len(requests))

        def run(changes):
            try:
                barrier.wait(timeout=10)
                with tenant_atomic(self.context):
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
                        cursor.execute("SET LOCAL lock_timeout = '10s'")
                    data = {
                        "userId": self.members[EmployeeRole.EMPLOYEE].user_id,
                        "reasonId": self.reason.pk, "comment": "Internal",
                        "operationId": str(uuid4()), "expectedVersion": 0, **changes,
                    }
                    try:
                        return assign_operator(context=self.context,
                                               conversation_id=self.conversation.pk, transfer=data).pk
                    except AssignmentConflict:
                        return "conflict"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(requests)) as pool:
            futures = [pool.submit(run, data) for data in requests]
            return [future.result(timeout=30) for future in futures]

    def assert_one_operation(self):
        for model in (ConversationTransfer, ConversationEvent, Notification, OutboxEvent):
            self.assertEqual(model.objects.count(), 1, model.__name__)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assignment_version, 1)

    def test_same_version_has_one_winner(self):
        results = self.run_concurrently([
            {}, {"userId": self.members[EmployeeRole.SUPERVISOR].user_id},
        ])
        self.assertEqual(results.count("conflict"), 1)
        self.assert_one_operation()

    def test_concurrent_replay_creates_exactly_one_operation(self):
        key = str(uuid4())
        results = self.run_concurrently([{"operationId": key}, {"operationId": key}])
        self.assertEqual(results[0], results[1])
        self.assertNotEqual(results[0], "conflict")
        self.assert_one_operation()

    def test_key_reused_on_another_conversation_is_rejected_without_changes(self):
        key = str(uuid4())
        self.run_concurrently([{"operationId": key}])
        other = Conversation.objects.create(
            organization=self.organization, channel=self.conversation.channel,
            contact=self.conversation.contact,
        )
        with self.assertRaises(AssignmentConflict):
            assign_operator(context=self.context, conversation_id=other.pk, transfer={
                "userId": self.members[EmployeeRole.EMPLOYEE].user_id,
                "reasonId": self.reason.pk, "comment": "Internal",
                "expectedVersion": 0, "operationId": key,
            })
        other.refresh_from_db()
        self.assertIsNone(other.assigned_operator_id)
        self.assertEqual(other.assignment_version, 0)
        self.assert_one_operation()
