from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.db import transaction
from django.test import TransactionTestCase

from chatballs.conversations.models import ControlMode
from chatballs.conversations.participant_services import add_participant, remove_participant
from chatballs.conversations.participant_test_base import ParticipantTestBase
from chatballs.conversations.realtime import conversation_group
from chatballs.identity.group_models import EmployeeGroup, EmployeeGroupMember
from chatballs.tenancy.database import tenant_atomic
from chatballs_backend.asgi_app import application


class ParticipantRealtimeTests(TransactionTestCase):
    def setUp(self):
        ParticipantTestBase.setUpTestData.__func__(type(self))
        self.group = EmployeeGroup.objects.create(organization=self.organization, name="Private")
        self.conversation.group = self.group
        self.conversation.control_mode = ControlMode.HUMAN
        self.conversation.save(update_fields=["group", "control_mode"])
        with tenant_atomic(self.context):
            self.row, _ = add_participant(
                context=self.context, conversation_id=self.conversation.pk,
                membership_id=self.members[1].pk, reason="Internal",
            )

    async def connect(self, member):
        socket = WebsocketCommunicator(
            application, f"/ws/organizations/{self.organization.public_id}/conversations/",
        )
        socket.scope["user"] = member.user
        self.assertTrue((await socket.connect(timeout=5))[0])
        await socket.send_json_to({"type": "watch", "conversationId": self.conversation.pk})
        return socket

    @database_sync_to_async
    def revoke(self):
        with tenant_atomic(self.context):
            remove_participant(
                context=self.context, conversation_id=self.conversation.pk,
                participant_id=self.row.pk, reason="Finished",
            )

    async def emit(self):
        await get_channel_layer().group_send(conversation_group(self.conversation.pk), {
            "type": "fanout", "payload": {
                "type": "conversation.changed", "conversationId": self.conversation.pk,
            },
        })

    async def test_removal_event_and_future_delivery_use_post_operation_access(self):
        participant = await self.connect(self.members[1])
        assignee = await self.connect(self.members[0])
        outsider = await self.connect(self.members[2])
        try:
            for socket in (participant, assignee):
                self.assertEqual((await socket.receive_json_from(timeout=5))["type"], "watching")
            self.assertTrue(await outsider.receive_nothing(timeout=0.2))
            await self.revoke()
            self.assertEqual((await participant.receive_json_from(timeout=5)), {"type": "inbox.changed"})
            events = [await assignee.receive_json_from(timeout=5) for _ in range(2)]
            self.assertEqual({event["type"] for event in events}, {"inbox.changed", "conversation.changed"})
            self.assertEqual(await outsider.receive_json_from(timeout=5), {"type": "inbox.changed"})
            self.assertTrue(await participant.receive_nothing(timeout=0.2))
            await self.emit()
            self.assertEqual((await assignee.receive_json_from(timeout=5))["type"], "conversation.changed")
            self.assertTrue(await participant.receive_nothing(timeout=0.2))
            await participant.send_json_to({"type": "watch", "conversationId": self.conversation.pk})
            self.assertTrue(await participant.receive_nothing(timeout=0.2))
        finally:
            for socket in (participant, assignee, outsider):
                await socket.disconnect()

    async def test_removal_preserves_socket_delivery_with_independent_group_access(self):
        await database_sync_to_async(EmployeeGroupMember.objects.create)(
            organization=self.organization, group=self.group, employee=self.members[1],
        )
        socket = await self.connect(self.members[1])
        try:
            self.assertEqual((await socket.receive_json_from(timeout=5))["type"], "watching")
            await self.revoke()
            events = [await socket.receive_json_from(timeout=5) for _ in range(2)]
            self.assertEqual({event["type"] for event in events}, {"inbox.changed", "conversation.changed"})
        finally:
            await socket.disconnect()

    async def test_rolled_back_change_does_not_publish_composition(self):
        socket = await self.connect(self.members[0])

        def aborted_change():
            try:
                with tenant_atomic(self.context), transaction.atomic():
                    remove_participant(
                        context=self.context, conversation_id=self.conversation.pk,
                        participant_id=self.row.pk, reason="Abort",
                    )
                    raise RuntimeError("Abort")
            except RuntimeError:
                pass

        try:
            self.assertEqual((await socket.receive_json_from(timeout=5))["type"], "watching")
            await database_sync_to_async(aborted_change)()
            self.assertTrue(await socket.receive_nothing(timeout=0.3))
        finally:
            await socket.disconnect()
