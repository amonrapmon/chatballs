from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase

from chatballs.conversations import test_authorization as visibility_tests
from chatballs.conversations.realtime import conversation_group, inbox_group
from chatballs.identity.models import EmployeeRole, OrganizationMembership
from chatballs.identity.supervision_models import EmployeeGroupSupervision
from chatballs_backend.asgi_app import application


class SupervisorRealtimeTests(TransactionTestCase):
    _employee = visibility_tests.ConversationVisibilityTests._employee
    _conversation = visibility_tests.ConversationVisibilityTests._conversation

    def setUp(self):
        visibility_tests.ConversationVisibilityTests.setUp(self)
        self.employee.role = EmployeeRole.SUPERVISOR
        self.employee.save(update_fields=["role"])
        EmployeeGroupSupervision.objects.create(employee=self.employee, group=self.support)

    def test_session_reports_current_control_area_and_actions(self):
        response = self.client.get("/api/v1/auth/session/")
        self.assertEqual(response.status_code, 200)
        membership = response.json()["user"]["memberships"][0]
        self.assertEqual(membership["supervisedGroups"], [{"id": self.support.pk, "name": self.support.name}])
        self.assertEqual(set(membership["supervisionCapabilities"]), {
            "conversations.view", "conversations.assign", "conversations.transfer",
            "conversations.participants", "conversations.comment",
        })
        EmployeeGroupSupervision.objects.filter(employee=self.employee).delete()
        membership = self.client.get("/api/v1/auth/session/").json()["user"]["memberships"][0]
        self.assertEqual(membership["supervisedGroups"], [])
        self.assertEqual(membership["supervisionCapabilities"], [])

    async def connect_socket(self):
        socket = WebsocketCommunicator(
            application, f"/ws/organizations/{self.organization.public_id}/conversations/",
        )
        socket.scope["user"] = self.employee.user
        connected, _ = await socket.connect(timeout=5)
        self.assertTrue(connected)
        await socket.send_json_to({"type": "watch", "conversationId": self.support_conversation.pk})
        self.assertEqual(await socket.receive_json_from(timeout=5), {
            "type": "watching", "conversationId": self.support_conversation.pk,
        })
        return socket

    async def emit(self):
        layer = get_channel_layer()
        await layer.group_send(conversation_group(self.support_conversation.pk), {
            "type": "fanout", "payload": {
                "type": "conversation.changed", "conversationId": self.support_conversation.pk,
            },
        })
        await layer.group_send(inbox_group(self.organization.pk), {
            "type": "fanout", "payload": {"type": "inbox.changed"},
        })

    async def check_revocation(self, change, *, blocked=False):
        socket = await self.connect_socket()
        try:
            await self.emit()
            before = [await socket.receive_json_from(timeout=5) for _ in range(2)]
            self.assertEqual({item["type"] for item in before}, {"conversation.changed", "inbox.changed"})
            await database_sync_to_async(change)()
            await self.emit()
            if not blocked:
                self.assertEqual(await socket.receive_json_from(timeout=5), {"type": "inbox.changed"})
            self.assertTrue(await socket.receive_nothing(timeout=0.3))
            await socket.send_json_to({"type": "watch", "conversationId": self.support_conversation.pk})
            self.assertTrue(await socket.receive_nothing(timeout=0.3))
        finally:
            await socket.disconnect()

    async def test_open_socket_rechecks_revoked_control_group(self):
        await self.check_revocation(lambda: EmployeeGroupSupervision.objects.filter(employee=self.employee).delete())

    async def test_open_socket_rechecks_current_role(self):
        await self.check_revocation(lambda: OrganizationMembership.objects.filter(pk=self.employee.pk).update(role=EmployeeRole.EMPLOYEE))

    async def test_blocked_open_socket_receives_no_delivery(self):
        await self.check_revocation(self.employee.block, blocked=True)

    async def test_deactivated_user_receives_no_delivery(self):
        await self.check_revocation(lambda: self.employee.user.__class__.objects.filter(pk=self.employee.user_id).update(is_active=False), blocked=True)

    async def test_merged_comment_delivery_rechecks_control_and_hides_reply_assistance(self):
        socket = await self.connect_socket()
        layer = get_channel_layer()
        comment = {"type": "comments.changed", "conversationId": self.support_conversation.pk}
        assistance = {"type": "reply_assistance.changed", "conversationId": self.support_conversation.pk}
        group = conversation_group(self.support_conversation.pk)
        try:
            await layer.group_send(group, {"type": "fanout", "payload": comment})
            self.assertEqual(await socket.receive_json_from(timeout=5), comment)
            await layer.group_send(group, {"type": "fanout", "payload": assistance})
            self.assertTrue(await socket.receive_nothing(timeout=0.3))
            await database_sync_to_async(lambda: EmployeeGroupSupervision.objects.filter(employee=self.employee).delete())()
            await layer.group_send(group, {"type": "fanout", "payload": comment})
            self.assertTrue(await socket.receive_nothing(timeout=0.3))
        finally:
            await socket.disconnect()
