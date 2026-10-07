from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from chatballs.conversations.participant_models import ConversationParticipant
from chatballs.conversations.participant_test_base import ParticipantTestBase
from chatballs.identity.models import Organization


class ParticipantModelTests(ParticipantTestBase):
    def test_join_leave_and_rejoin_preserve_history_and_assignment(self):
        row = self.row()
        row.save()
        self.assertIsNotNone(row.joined_at)
        self.assertEqual(list(ConversationParticipant.objects.active()), [row])
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.row().save()
        row.left_by = self.members[2]
        row.left_at = timezone.now()
        row.leave_reason = "Consultation completed"
        row.save()
        rejoined = self.row(joined_by=self.members[2], join_reason="Follow-up consultation")
        rejoined.save()
        row.refresh_from_db()
        self.assertEqual(row.joined_by_id, self.members[0].pk)
        self.assertEqual(row.left_by_id, self.members[2].pk)
        self.assertEqual(row.join_reason, "Specialist consultation")
        self.assertEqual(row.leave_reason, "Consultation completed")
        self.assertEqual(list(ConversationParticipant.objects.active()), [rejoined])
        self.assertEqual(ConversationParticipant.objects.count(), 2)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.members[0].user_id)

    def test_database_requires_reasons_complete_exit_and_chronological_times(self):
        row = self.row()
        row.save()
        for changes in (
            {"join_reason": ""},
            {"left_at": timezone.now()},
            {"left_by": self.members[0]},
            {"leave_reason": "Incomplete exit"},
            {"left_at": timezone.now(), "left_by": self.members[0]},
            {"left_at": row.joined_at - timedelta(seconds=1),
             "left_by": self.members[0], "leave_reason": "Too early"},
        ):
            with self.subTest(changes=changes), self.assertRaises(IntegrityError), transaction.atomic():
                ConversationParticipant.objects.filter(pk=row.pk).update(**changes)

    def test_additional_count_excludes_current_responsible_and_completed_rows(self):
        self.row(membership=self.members[0]).save()
        row = self.row()
        row.save()
        self.assertEqual(self.conversation.participants.active().count(), 2)
        self.assertEqual(self.conversation.participants.additional().count(), 1)
        self.conversation.assigned_operator = self.members[1].user
        self.conversation.save(update_fields=["assigned_operator"])
        self.assertEqual(list(self.conversation.participants.additional().values_list(
            "membership_id", flat=True,
        )), [self.members[0].pk])
        self.conversation.assigned_operator = None
        self.conversation.save(update_fields=["assigned_operator"])
        self.assertEqual(self.conversation.participants.additional().count(), 2)
        row.left_at = timezone.now()
        row.left_by = self.members[2]
        row.leave_reason = "Completed"
        row.save()
        self.assertEqual(self.conversation.participants.additional().count(), 1)

    def test_limit_default_zero_and_reduction_preserve_existing_rows(self):
        self.assertEqual(self.organization.additional_participant_limit, 5)
        self.row().save()
        self.organization.additional_participant_limit = 0
        self.organization.save(update_fields=["additional_participant_limit"])
        self.organization.refresh_from_db()
        self.assertEqual(self.organization.additional_participant_limit, 0)
        self.assertEqual(self.conversation.participants.additional().count(), 1)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.members[0].user_id)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Organization.objects.filter(pk=self.organization.pk).update(additional_participant_limit=-1)

    def test_model_checks_every_tenant_relation_and_derives_organization(self):
        for changes in (
            {"organization": self.foreign}, {"conversation": self.foreign_conversation},
            {"membership": self.foreign_member}, {"joined_by": self.foreign_member},
            {"left_by": self.foreign_member, "left_at": timezone.now(), "leave_reason": "Completed"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.row(**changes).save()
        row = self.row(organization_id=None)
        row.save()
        self.assertEqual(row.organization_id, self.organization.pk)
