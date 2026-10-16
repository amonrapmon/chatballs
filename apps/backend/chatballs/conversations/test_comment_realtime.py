from uuid import uuid4

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.test import override_settings
from django.utils import timezone

from chatballs.conversations.comment_services import create_comment
from chatballs.conversations.comment_test_base import CommentTransactionTestBase
from chatballs.conversations.models import Conversation
from chatballs.conversations.participant_models import ConversationParticipant
from chatballs.identity.group_models import EmployeeGroup, EmployeeGroupMember
from chatballs.identity.models import HumanUser, OrganizationMembership
from chatballs.identity.supervision_models import EmployeeGroupSupervision
from chatballs_backend.asgi_app import application


@override_settings(CHANNEL_LAYERS={"default": {
    "BACKEND": "channels_redis.core.RedisChannelLayer",
    "CONFIG": {"hosts": [settings.CACHES["default"]["LOCATION"]], "prefix": "t056-comments"},
}})
class CommentRealtimeTests(CommentTransactionTestBase):
    def socket(self, user, organization=None):
        organization = organization or self.organization
        socket = WebsocketCommunicator(
            application, f"/ws/organizations/{organization.public_id}/conversations/",
        )
        socket.scope["user"] = user
        return socket

    async def watch(self, user):
        socket = self.socket(user)
        connected, _ = await socket.connect(timeout=5)
        self.assertTrue(connected)
        await socket.send_json_to({"type": "watch", "conversationId": self.conversation.pk})
        self.assertEqual(await socket.receive_json_from(timeout=5), {
            "type": "watching", "conversationId": self.conversation.pk,
        })
        return socket

    @database_sync_to_async
    def append(self, operation=None, rollback=False):
        with transaction.atomic():
            result = create_comment(
                context=self.context, conversation_id=self.conversation.pk,
                audience="INTERNAL", text="Private comment", operation_id=operation or uuid4(),
            )
            if rollback:
                transaction.set_rollback(True)
            return result[0].pk

    async def test_commit_delivers_only_invalidation_to_employee_watcher_once(self):
        watcher = await self.watch(self.author)
        inbox = self.socket(self.author)
        self.assertTrue((await inbox.connect(timeout=5))[0])
        foreign = self.socket(self.foreign_author, self.foreign)
        self.assertTrue((await foreign.connect(timeout=5))[0])
        operation = uuid4()
        await self.append(operation, rollback=True)
        self.assertTrue(await watcher.receive_nothing(timeout=0.2))
        await self.append(operation)
        self.assertEqual(await watcher.receive_json_from(timeout=5), {
            "type": "comments.changed", "conversationId": self.conversation.pk,
        })
        await self.append(operation)
        for socket in (watcher, inbox, foreign):
            self.assertTrue(await socket.receive_nothing(timeout=0.2))
            await socket.disconnect()

    async def test_customer_and_foreign_membership_cannot_connect(self):
        for user in (AnonymousUser(), self.foreign_author):
            socket = self.socket(user)
            connected, code = await socket.connect(timeout=5)
            self.assertFalse(connected)
            self.assertEqual(code, 4403)
            await socket.disconnect()

    @database_sync_to_async
    def prepare_reader(self, basis):
        group = EmployeeGroup.objects.create(organization=self.organization, name="Restricted")
        Conversation.objects.filter(pk=self.conversation.pk).update(group=group)
        user = HumanUser.objects.create_user(email=f"{basis}@comments.test")
        member = OrganizationMembership.objects.create(
            organization=self.organization, user=user,
            role="ADMIN" if basis == "role" else "EMPLOYEE",
        )
        if basis == "supervision":
            member.role = "SUPERVISOR"
            member.save(update_fields=["role"])
            EmployeeGroupSupervision.objects.create(employee=member, group=group)
        if basis == "participant":
            ConversationParticipant.objects.create(
                organization=self.organization, conversation=self.conversation,
                membership=member, joined_by=self.membership, join_reason="Consultation",
            )
        elif basis == "group":
            EmployeeGroupMember.objects.create(
                organization=self.organization, employee=member, group=group,
            )
        elif basis == "assignment":
            Conversation.objects.filter(pk=self.conversation.pk).update(assigned_operator=user)
        return member

    @database_sync_to_async
    def revoke(self, member, basis):
        if basis == "supervision":
            EmployeeGroupSupervision.objects.filter(employee=member).delete()
        elif basis == "participant":
            ConversationParticipant.objects.filter(membership=member).update(
                left_at=timezone.now(), left_by=self.membership, leave_reason="Finished",
            )
        elif basis == "group":
            EmployeeGroupMember.objects.filter(employee=member).delete()
        elif basis == "assignment":
            Conversation.objects.filter(pk=self.conversation.pk).update(assigned_operator=None)
        elif basis == "role":
            OrganizationMembership.objects.filter(pk=member.pk).update(role="EMPLOYEE")
        elif basis == "blocked":
            OrganizationMembership.objects.filter(pk=member.pk).update(blocked_at=timezone.now())
        elif basis == "inactive":
            HumanUser.objects.filter(pk=member.user_id).update(is_active=False)
        elif basis == "deleted":
            OrganizationMembership.objects.filter(pk=member.pk).delete()

    async def assert_revoked(self, basis):
        member = await self.prepare_reader(basis if basis in {"group", "assignment", "participant", "supervision"} else "role")
        watcher = await self.watch(member.user)
        await self.append()
        await watcher.receive_json_from(timeout=5)
        await self.revoke(member, basis)
        await self.append()
        self.assertTrue(await watcher.receive_nothing(timeout=0.3))
        await watcher.disconnect()

    async def test_ended_participation_stops_delivery(self):
        await self.assert_revoked("participant")

    async def test_revoked_supervision_stops_comment_delivery(self):
        await self.assert_revoked("supervision")

    async def test_role_downgrade_stops_delivery(self):
        await self.assert_revoked("role")

    async def test_group_removal_stops_delivery(self):
        await self.assert_revoked("group")

    async def test_unassignment_stops_delivery(self):
        await self.assert_revoked("assignment")

    async def test_membership_block_stops_delivery(self):
        await self.assert_revoked("blocked")

    async def test_global_deactivation_stops_delivery(self):
        await self.assert_revoked("inactive")

    async def test_membership_removal_stops_delivery(self):
        await self.assert_revoked("deleted")

    async def test_other_access_basis_survives_participation_end(self):
        member = await self.prepare_reader("participant")
        await database_sync_to_async(OrganizationMembership.objects.filter(pk=member.pk).update)(role="ADMIN")
        watcher = await self.watch(member.user)
        await self.revoke(member, "participant")
        await self.append()
        self.assertEqual((await watcher.receive_json_from(timeout=5))["type"], "comments.changed")
        await watcher.disconnect()
