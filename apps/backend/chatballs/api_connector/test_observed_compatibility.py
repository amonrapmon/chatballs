from django.test import TestCase

from chatballs.api_connector.observed_test_fixture import ObservedOutgoingFixture
from chatballs.conversations.models import Conversation, LifecycleState, Message
from chatballs.identity.models import AuditEvent, EmployeeRole, HumanUser, OrganizationMembership
from chatballs.native_mirror.supersession import current_revision
from chatballs.testing import TenantAPIClient


class ObservedOutgoingCompatibilityTests(ObservedOutgoingFixture, TestCase):
    def test_provider_replay_after_reopen_leaves_the_new_conversation_untouched(self):
        previous = self.open_conversation()
        event = self.observed()
        self.assertEqual(self.send(event).status_code, 202)
        prefix = f"/api/v1/organizations/{self.organization.public_id}"
        closed = self.client.post(f"{prefix}/conversations/{previous.pk}/close/", {}, format="json")
        self.assertEqual(closed.status_code, 200, closed.data)

        incoming = self.incoming(event_id="in-2", external_id="guest-message-2")
        self.assertEqual(self.send(incoming).status_code, 202)
        reopened = Conversation.objects.get(previous_conversation=previous, lifecycle=LifecycleState.OPEN)

        self.assertEqual(self.send(event).status_code, 202)
        duplicate = self.send(self.observed(event_id="replayed-with-new-event-id"))
        self.assertEqual(duplicate.status_code, 202, duplicate.data)

        mirrored = Message.objects.filter(
            conversation__connection=self.integration,
            conversation__external_chat_id=previous.external_chat_id,
            connector_origin="EXTERNAL_OBSERVED",
        )
        self.assertEqual(list(mirrored.values_list("conversation_id", flat=True)), [previous.pk])
        self.assertEqual(current_revision(conversation_id=previous.pk), 1)
        self.assertEqual(current_revision(conversation_id=reopened.pk), 0)

    def test_employee_without_manage_permission_cannot_change_mirroring(self):
        employee = HumanUser.objects.create_user(email="connector-observed-employee@example.test")
        OrganizationMembership.objects.create(
            organization=self.organization, user=employee, role=EmployeeRole.EMPLOYEE,
        )
        staff = TenantAPIClient()
        staff.force_authenticate(employee)
        updates = AuditEvent.objects.filter(
            object_id=str(self.integration.pk), action="integrations.integration_updated",
        )
        audit_count = updates.count()

        response = staff.patch(
            f"/api/v1/organizations/{self.organization.public_id}/integrations/{self.integration.pk}/",
            {"config": {"mirrorExternalOutgoingEnabled": False}},
            format="json",
        )

        self.assertEqual(response.status_code, 403, response.data)
        self.integration.refresh_from_db()
        self.assertIs(self.integration.config["mirrorExternalOutgoingEnabled"], True)
        self.assertEqual(updates.count(), audit_count)
