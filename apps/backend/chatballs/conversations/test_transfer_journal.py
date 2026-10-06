from uuid import uuid4

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from chatballs.conversations.models import Message
from chatballs.conversations.serializers import conversation_payload
from chatballs.conversations.transfer_models import ConversationTransfer
from chatballs.conversations.transfer_services import disable_reason, record_transfer, save_reason
from chatballs.conversations.transfer_test_base import TransferTestBase
from chatballs.events.models import OutboxEvent
from chatballs.identity.models import EmployeeRole
from chatballs.notifications.models import Notification


class TransferJournalTests(TransferTestBase):
    def record(self, **changes):
        return record_transfer(**{
            "context": self.context, "conversation_id": self.conversation.pk,
            "previous_operator_id": self.members[EmployeeRole.ADMIN].user_id,
            "new_operator_id": self.members[EmployeeRole.EMPLOYEE].user_id,
            "reason_id": self.reason.pk, "comment": "Internal details", "operation_id": uuid4(),
            **changes,
        })

    def test_records_all_fields_and_preserves_snapshot_after_edit_disable(self):
        start = timezone.now()
        operation_id = uuid4()
        row = self.record(operation_id=operation_id)
        self.assertEqual(row.organization_id, self.organization.pk)
        self.assertEqual(row.conversation_id, self.conversation.pk)
        self.assertEqual(row.previous_operator_id, self.members[EmployeeRole.ADMIN].user_id)
        self.assertEqual(row.new_operator_id, self.members[EmployeeRole.EMPLOYEE].user_id)
        self.assertEqual(row.initiated_by_id, self.context.actor_user.pk)
        self.assertEqual(row.operation_id, operation_id)
        self.assertTrue(start <= row.occurred_at <= timezone.now())
        save_reason(context=self.context, reason_id=self.reason.pk, data={"code": "renamed", "name": "Changed"})
        disable_reason(context=self.context, reason_id=self.reason.pk)
        row.refresh_from_db()
        self.assertEqual((row.reason_code, row.reason_name, row.comment),
                         ("specialist", "Specialist needed", "Internal details"))
        from django.db.models.deletion import ProtectedError

        with self.assertRaises(ProtectedError):
            self.reason.delete()

    def test_disabled_or_foreign_reason_cannot_be_used(self):
        disable_reason(context=self.context, reason_id=self.reason.pk)
        for reason_id in (self.reason.pk, self.foreign_reason.pk):
            with self.assertRaises(ValidationError):
                self.record(reason_id=reason_id)
        self.assertFalse(ConversationTransfer.objects.exists())

    def test_first_assignment_can_have_no_previous_operator(self):
        row = self.record(previous_operator_id=None, comment="")
        self.assertIsNone(row.previous_operator_id)
        self.assertEqual(row.comment, "")

    def test_foreign_blocked_and_inactive_recipient_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.record(new_operator_id=self.foreign_user.pk)
        employee = self.members[EmployeeRole.EMPLOYEE]
        employee.blocked_at = timezone.now()
        employee.save(update_fields=["blocked_at"])
        with self.assertRaises(ValidationError):
            self.record()
        employee.blocked_at = None
        employee.save(update_fields=["blocked_at"])
        employee.user.is_active = False
        employee.user.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            self.record()
        self.assertFalse(ConversationTransfer.objects.exists())

    def test_operation_unique_and_internal_details_do_not_enter_messages_or_events(self):
        counts = (Message.objects.count(), Notification.objects.count(), OutboxEvent.objects.count())
        row = self.record()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.record(operation_id=row.operation_id)
        self.assertEqual(ConversationTransfer.objects.count(), 1)
        self.assertEqual(counts, (Message.objects.count(), Notification.objects.count(), OutboxEvent.objects.count()))
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.members[EmployeeRole.ADMIN].user_id)
        payload = str(conversation_payload(self.conversation, detailed=True))
        self.assertNotIn("Internal details", payload)
        self.assertNotIn("Specialist needed", payload)

    def test_no_access_to_hidden_or_foreign_conversation(self):
        from chatballs.identity.group_models import EmployeeGroup
        from chatballs.tenancy.context import TenantContext

        self.conversation.group = EmployeeGroup.objects.create(organization=self.organization, name="Private")
        self.conversation.save(update_fields=["group"])
        with self.assertRaises(self.conversation.DoesNotExist):
            self.record(context=TenantContext.for_membership(self.members[EmployeeRole.EMPLOYEE]))
        with self.assertRaises(self.conversation.DoesNotExist):
            self.record(context=TenantContext.for_membership(self.foreign_user.memberships.get()))
