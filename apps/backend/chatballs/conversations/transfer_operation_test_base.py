from uuid import uuid4

from chatballs.conversations.assignment_policy import AssignmentPolicy
from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.models import Message
from chatballs.conversations.transfer_models import ConversationTransfer
from chatballs.conversations.transfer_test_base import TransferTestBase
from chatballs.events.models import OutboxEvent
from chatballs.identity.models import EmployeeRole
from chatballs.notifications.models import Notification


class TransferOperationTestBase(TransferTestBase):
    def setUp(self):
        super().setUp()
        self.policy = AssignmentPolicy.objects.get(organization=self.organization)
        self.policy.busy = False
        self.policy.break_allowed = False
        self.policy.save(update_fields=["busy", "break_allowed"])
        self.root = f"/api/v1/organizations/{self.organization.public_id}/conversations/"
        self.endpoint = f"{self.root}{self.conversation.pk}/assignee/"
        self.data = {
            "userId": self.members[EmployeeRole.EMPLOYEE].user_id,
            "reasonId": self.reason.pk, "comment": "Private transfer details",
            "expectedVersion": 0, "operationId": str(uuid4()),
        }

    def post(self, **changes):
        return self.client.post(self.endpoint, {**self.data, **changes}, format="json")

    def assert_no_transfer(self):
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.members[EmployeeRole.ADMIN].user_id)
        self.assertEqual(self.conversation.assignment_version, 0)
        for model in (ConversationTransfer, ConversationEvent, Notification, OutboxEvent, Message):
            self.assertFalse(model.objects.exists(), model.__name__)
