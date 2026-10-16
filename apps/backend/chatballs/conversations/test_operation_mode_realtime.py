"""Mode changes use the existing tenant socket and disclose no conversation IDs."""

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.db import transaction
from django.test import TransactionTestCase

from chatballs.identity.models import HumanUser, Organization, OrganizationMembership
from chatballs.identity.operation_modes import change_operation_mode, lock_organization
from chatballs.testing import tenant_context_for
from chatballs_backend.asgi_app import application


class OperationModeRealtimeTests(TransactionTestCase):
    def setUp(self):
        self.organization = Organization.objects.create(name="Socket", slug="socket-mode")
        self.owner = HumanUser.objects.create_user(email="owner@socket-mode.test")
        OrganizationMembership.objects.create(organization=self.organization, user=self.owner, role="OWNER")
        self.other = Organization.objects.create(name="Other", slug="other-socket-mode")
        self.foreign = HumanUser.objects.create_user(email="foreign@socket-mode.test")
        OrganizationMembership.objects.create(organization=self.other, user=self.foreign, role="ADMIN")

    async def test_mode_change_reaches_only_its_organization(self):
        own = WebsocketCommunicator(application, f"/ws/organizations/{self.organization.public_id}/conversations/")
        own.scope["user"] = self.owner
        foreign = WebsocketCommunicator(application, f"/ws/organizations/{self.other.public_id}/conversations/")
        foreign.scope["user"] = self.foreign
        self.assertTrue((await own.connect(timeout=10))[0])
        self.assertTrue((await foreign.connect(timeout=10))[0])
        try:
            await self._switch()
            events = [await own.receive_json_from(timeout=10) for _ in range(2)]
            self.assertIn({"type": "organization.changed"}, events)
            self.assertIn({"type": "inbox.changed"}, events)
            self.assertTrue(await foreign.receive_nothing(timeout=.1))
        finally:
            await own.disconnect()
            await foreign.disconnect()

    @database_sync_to_async
    def _switch(self):
        context = tenant_context_for(self.owner)
        with transaction.atomic():
            organization = lock_organization(self.organization.pk)
            change_operation_mode(context=context, organization=organization, mode="OPERATORS_ONLY")
