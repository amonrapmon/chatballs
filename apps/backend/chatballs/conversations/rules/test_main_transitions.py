"""Rules share domain facts with structured transfers and quality analysis."""

from datetime import timedelta
from uuid import uuid4

from django.test import TestCase

from chatballs.conversations.assignment import assign_operator
from chatballs.conversations.models import Message, MessageAuthor
from chatballs.conversations.quality.criteria import configure_quality
from chatballs.conversations.quality.models import QualityJob
from chatballs.conversations.quality.queue import QUALITY_REQUESTED
from chatballs.conversations.rules.rule_test_base import RuleScene
from chatballs.conversations.services import close_conversation
from chatballs.conversations.transfer_models import TransferReason
from chatballs.events.models import OutboxEvent


class MainTransitionRuleTests(RuleScene, TestCase):
    def test_structured_transfer_replaces_deadline_and_preserves_transfer_version(self):
        original = self.assign(self.operator)
        self.conversation.refresh_from_db()
        reason = TransferReason.objects.create(
            organization=self.organization, code="specialist", name="Specialist",
        )
        operation_id = uuid4()
        data = {
            "userId": self.colleague.user_id, "reasonId": reason.pk,
            "comment": "Internal transfer", "expectedVersion": self.conversation.assignment_version,
            "operationId": str(operation_id),
        }
        transfer = assign_operator(
            context=self.context, conversation_id=self.conversation.pk, transfer=data,
        )
        replacement = self.executions().exclude(pk=original.pk).get()
        original.refresh_from_db()
        self.assertEqual((original.status, original.reason), ("SKIPPED", "assignment_replaced"))
        self.assertEqual(replacement.source_event.operation_id, operation_id)
        self.assertEqual(replacement.source_event.responsible_id, self.colleague.user_id)
        self.assertEqual(
            replacement.scheduled_for,
            replacement.source_event.occurred_at + timedelta(minutes=10),
        )
        self.deliver(original)
        replay = assign_operator(
            context=self.context, conversation_id=self.conversation.pk, transfer=data,
        )
        self.assertEqual(replay.pk, transfer.pk)
        self.assertEqual(self.due_events(replacement).count(), 1)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.colleague.user_id)
        self.assertEqual(self.conversation.assignment_version, transfer.assignment_version)
        self.deliver(replacement)
        self.conversation.refresh_from_db()
        self.assertIsNone(self.conversation.assigned_operator_id)
        self.assertEqual(self.conversation.assignment_version, transfer.assignment_version + 1)
        transfer.refresh_from_db()
        self.assertEqual(transfer.new_operator_id, self.colleague.user_id)

    def test_close_cancels_return_and_schedules_quality_from_the_same_transaction(self):
        execution = self.assign(self.operator)
        configure_quality(context=self.context, enabled=True, criteria=[{
            "code": "resolution", "description": "Resolution", "scale": [0, 1],
        }])
        Message.objects.create(
            conversation=self.conversation, author_type=MessageAuthor.CONTACT, text="Question",
        )
        close_conversation(context=self.context, conversation_id=self.conversation.pk)
        execution.refresh_from_db()
        self.assertEqual((execution.status, execution.reason), ("SKIPPED", "conversation_not_open"))
        completion = self.conversation.domain_events.get(event_type="CLOSED")
        job = QualityJob.objects.get(conversation=self.conversation)
        self.assertEqual(job.completion_event_id, completion.operation_id)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type=QUALITY_REQUESTED, aggregate_id=str(job.pk),
        ).count(), 1)
        self.deliver(execution)
        self.assertFalse(self.conversation.messages.filter(system_event="ASSIGNMENT_EXPIRED").exists())
