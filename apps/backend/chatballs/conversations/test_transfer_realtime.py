from uuid import uuid4

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.db import connection, transaction
from django.test import TransactionTestCase

from chatballs.conversations.assignment import assign_operator
from chatballs.conversations.transfer_test_base import TransferTestBase
from chatballs.events.handlers import dispatch
from chatballs.events.models import OutboxEvent
from chatballs.identity.models import EmployeeRole
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic
from chatballs_backend.asgi_app import application


class TransferRealtimeTests(TransactionTestCase):
    def setUp(self):
        TransferTestBase.setUpTestData.__func__(type(self))
        self.context = TenantContext.for_membership(self.members[EmployeeRole.OWNER])

    async def test_commit_reaches_recipient_and_rollback_emits_nothing(self):
        recipient = self.members[EmployeeRole.EMPLOYEE]
        socket = WebsocketCommunicator(application,
            f"/ws/organizations/{self.organization.public_id}/conversations/")
        socket.scope["user"] = recipient.user
        connected, _ = await socket.connect(timeout=10)
        self.assertTrue(connected)

        @database_sync_to_async
        def transfer(rollback):
            with tenant_atomic(self.context):
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
                assign_operator(context=self.context, conversation_id=self.conversation.pk, transfer={
                    "userId": recipient.user_id, "reasonId": self.reason.pk,
                    "comment": "Private", "operationId": str(uuid4()), "expectedVersion": 0,
                })
                if rollback:
                    transaction.set_rollback(True)
                else:
                    dispatch(OutboxEvent.objects.get())

        try:
            await transfer(True)
            self.assertTrue(await socket.receive_nothing(timeout=1))
            await transfer(False)
            events = [await socket.receive_json_from(timeout=10) for _ in range(3)]
            self.assertCountEqual(events, [
                {"type": "inbox.changed"}, {"type": "inbox.changed"},
                {"type": "notifications.changed"},
            ])
        finally:
            await socket.disconnect()
