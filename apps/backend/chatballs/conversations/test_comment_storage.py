from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from chatballs.conversations.audience import ConversationAudience
from chatballs.conversations.comment_models import ConversationComment
from chatballs.conversations.comment_test_base import CommentTestBase
from chatballs.conversations.models import Conversation, Message


class CommentStorageTests(CommentTestBase):
    def test_sequential_records_have_specific_author_and_server_time(self):
        start = timezone.now()
        first = self.comment(text="First", created_at=start - timedelta(days=365))
        second = self.comment(text="Second")
        end = timezone.now()
        rows = list(ConversationComment.objects.filter(conversation=self.conversation))
        self.assertEqual([row.pk for row in rows], [first.pk, second.pk])
        self.assertEqual([row.text for row in rows], ["First", "Second"])
        for row in rows:
            self.assertEqual(row.author_id, self.author.pk)
            self.assertEqual(row.organization_id, self.organization.pk)
            self.assertEqual(row.audience, ConversationAudience.INTERNAL)
            self.assertLessEqual(start, row.created_at)
            self.assertLessEqual(row.created_at, end)

    def test_note_and_conversation_state_stay_separate(self):
        now = timezone.now()
        Conversation.objects.filter(pk=self.conversation.pk).update(
            note="Existing note", note_author=self.author, note_updated_at=now,
            assigned_operator=self.author, assigned_at=now, waiting_since=now,
        )
        before = Conversation.objects.values().get(pk=self.conversation.pk)
        self.comment(text="First")
        self.comment(text="Second")
        self.assertEqual(Conversation.objects.values().get(pk=self.conversation.pk), before)
        self.assertEqual(Message.objects.filter(conversation=self.conversation).count(), 0)
        Conversation.objects.filter(pk=self.conversation.pk).update(note="Edited note")
        self.assertEqual(list(self.conversation.comments.values_list("text", flat=True)), ["First", "Second"])

    def test_model_requires_explicit_internal_audience_nonempty_text_and_member_author(self):
        for changes in (
            {"audience": ""}, {"audience": "PUBLIC"}, {"audience": "unknown"},
            {"text": " \n\t"}, {"text": None}, {"author_id": None},
            {"author_id": self.foreign_author.pk},
            {"conversation_id": self.foreign_conversation.pk},
            {"organization_id": self.foreign.pk},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.row(**changes).save()

    def test_operation_unique_per_organization_and_history_cannot_be_overwritten(self):
        row = self.comment()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.comment(operation_id=row.operation_id)
        foreign = self.comment(
            organization_id=self.foreign.pk, conversation_id=self.foreign_conversation.pk,
            author_id=self.foreign_author.pk, operation_id=row.operation_id,
        )
        self.assertNotEqual(row.pk, foreign.pk)
        row.text = "Replacement"
        with self.assertRaises(ValidationError):
            row.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.row(pk=row.pk).save()
        row.refresh_from_db()
        self.assertEqual(row.text, "Internal discussion")
        with self.assertRaises(ProtectedError):
            self.author.delete()
