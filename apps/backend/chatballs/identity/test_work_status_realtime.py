"""Socket lifecycle and availability delivery with current tenant rights."""

from contextlib import AsyncExitStack
from uuid import uuid4

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.db import transaction
from django.utils import timezone

from chatballs.identity.models import EmployeeRole, HumanUser, OrganizationMembership
from chatballs.identity.work_status_codes import WorkStatus
from chatballs.identity.work_status_models import WorkStatusOperation
from chatballs.identity.work_status_testing import WorkStatusTestBase
from chatballs_backend.asgi_app import application


class WorkStatusRealtimeTests(WorkStatusTestBase):
    def setUp(self):
        super().setUp()
        self.colleague_user = HumanUser.objects.create(email="status-socket@status.test")
        self.colleague = OrganizationMembership.objects.create(
            organization=self.organization, user=self.colleague_user, role=EmployeeRole.EMPLOYEE,
        )

    async def connect(self, stack, user, organization=None, accepted=True):
        organization = organization or self.organization
        communicator = WebsocketCommunicator(
            application, f"/ws/organizations/{organization.public_id}/conversations/",
        )
        communicator.scope["user"] = user
        connected, code = await communicator.connect(timeout=5)
        self.assertEqual(connected, accepted)
        if not accepted:
            self.assertEqual(code, 4403)
        async def disconnect():
            if not communicator.future.done():
                await communicator.disconnect()

        stack.push_async_callback(disconnect)
        return communicator

    @database_sync_to_async
    def snapshot(self):
        self.membership.refresh_from_db()
        return (
            self.membership.work_status, self.membership.work_status_version,
            self.membership.work_status_changed_at,
            WorkStatusOperation.objects.filter(membership=self.membership).count(),
        )

    async def test_event_reaches_only_current_organization_and_noop_replay_are_silent(self):
        async with AsyncExitStack() as stack:
            own = await self.connect(stack, self.user)
            colleague = await self.connect(stack, self.colleague_user)
            # Same global human, another organization: no cross-tenant event.
            foreign = await self.connect(stack, self.user, self.foreign)
            key = uuid4()
            await database_sync_to_async(self.change)(WorkStatus.BREAK, key=key)
            expected = {"type": "work_status.changed", "userId": self.user.pk}
            self.assertEqual(await own.receive_json_from(timeout=5), expected)
            self.assertEqual(await colleague.receive_json_from(timeout=5), expected)
            self.assertTrue(await foreign.receive_nothing(timeout=0.2))
            await database_sync_to_async(self.change)(WorkStatus.BREAK, 1)
            await database_sync_to_async(self.change)(WorkStatus.BREAK, 0, key)
            self.assertTrue(await own.receive_nothing(timeout=0.2))
            self.assertTrue(await colleague.receive_nothing(timeout=0.2))

    async def test_open_ping_disconnect_and_reconnect_do_not_change_work_status(self):
        async with AsyncExitStack() as stack:
            await database_sync_to_async(self.change)(WorkStatus.READY)
            before = await self.snapshot()
            communicator = await self.connect(stack, self.user)
            await communicator.send_json_to({"type": "ping"})
            self.assertTrue(await communicator.receive_nothing(timeout=0.2))
            await communicator.disconnect()
            self.assertEqual(await self.snapshot(), before)
            reconnected = await self.connect(stack, self.user)
            await reconnected.send_json_to({"type": "ping"})
            self.assertTrue(await reconnected.receive_nothing(timeout=0.2))
            self.assertEqual(await self.snapshot(), before)

    async def test_delivery_rechecks_block_and_global_inactivity_after_connection(self):
        async with AsyncExitStack() as stack:
            blocked = await self.connect(stack, self.colleague_user)

            @database_sync_to_async
            def prepare():
                user = HumanUser.objects.create(email="inactive-socket@status.test")
                OrganizationMembership.objects.create(organization=self.organization, user=user)
                return user

            inactive_user = await prepare()
            inactive = await self.connect(stack, inactive_user)

            @database_sync_to_async
            def revoke():
                OrganizationMembership.objects.filter(pk=self.colleague.pk).update(blocked_at=timezone.now())
                HumanUser.objects.filter(pk=inactive_user.pk).update(is_active=False)

            await revoke()

            await database_sync_to_async(self.change)()
            self.assertTrue(await blocked.receive_nothing(timeout=0.2))
            self.assertTrue(await inactive.receive_nothing(timeout=0.2))
            await self.connect(stack, self.colleague_user, accepted=False)
            await self.connect(stack, inactive_user, accepted=False)

    async def test_rollback_never_publishes_and_foreign_nonmember_cannot_connect(self):
        async with AsyncExitStack() as stack:
            communicator = await self.connect(stack, self.user)
            await self.connect(stack, self.colleague_user, self.foreign, accepted=False)

            @database_sync_to_async
            def rollback():
                try:
                    with transaction.atomic():
                        self.change()
                        raise RuntimeError("rollback")
                except RuntimeError:
                    pass

            await rollback()
            self.assertTrue(await communicator.receive_nothing(timeout=0.2))
            self.assertEqual((await self.snapshot())[:2], (WorkStatus.UNAVAILABLE, 0))
