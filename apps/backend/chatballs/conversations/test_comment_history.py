from django.db import connection
from django.utils import timezone

from chatballs.api.pagination import window
from chatballs.conversations.audience import ConversationAudience
from chatballs.conversations.comment_models import ConversationComment
from chatballs.conversations.comment_test_base import CommentTestBase
from chatballs.conversations.history_selectors import conversation_records
from chatballs.conversations.models import Message, MessageAuthor
from chatballs.conversations.selectors import (
    MESSAGES_NEWER_KEYS,
    MESSAGES_OLDER_KEYS,
    conversation_messages,
)
from chatballs.testing import TenantAPIClient


class CommentHistoryTests(CommentTestBase):
    def records(self):
        return conversation_records(self.conversation, audience=ConversationAudience.INTERNAL)

    def test_tied_timestamps_paginate_both_directions_without_gaps_or_duplicates(self):
        rows = [self.comment(text=f"Comment {index}") for index in range(9)]
        tied_at = timezone.now()
        self.records().update(created_at=tied_at)
        self.comment(conversation_id=self.make_conversation(self.organization, "other").pk)
        self.comment(
            organization_id=self.foreign.pk, conversation_id=self.foreign_conversation.pk,
            author_id=self.foreign_author.pk,
        )
        for keys, expected in (
            (MESSAGES_OLDER_KEYS, [row.pk for row in reversed(rows)]),
            (MESSAGES_NEWER_KEYS, [row.pk for row in rows]),
        ):
            with self.subTest(keys=keys):
                collected, cursor = [], None
                for _ in range(5):
                    page = window(self.records(), keys=keys, limit=2, after=cursor)
                    collected.extend(row.pk for row in page.items)
                    if not page.has_more:
                        break
                    cursor = page.cursor
                self.assertEqual(collected, expected)
                self.assertIsNone(page.cursor)

    def test_new_comments_do_not_shift_public_windows_or_deltas(self):
        messages = [Message.objects.create(
            conversation=self.conversation, author_type=MessageAuthor.CONTACT, text=f"Public {index}"
        ) for index in range(5)]
        snapshot = list(Message.objects.values())
        initial = window(conversation_messages(self.conversation), keys=MESSAGES_OLDER_KEYS, limit=2)
        comments = [self.comment() for _ in range(7)]
        older = window(
            conversation_messages(self.conversation), keys=MESSAGES_OLDER_KEYS,
            limit=2, after=initial.cursor,
        )
        self.assertEqual([row.pk for row in older.items], [messages[2].pk, messages[1].pk])
        delta = window(
            conversation_messages(self.conversation), keys=MESSAGES_NEWER_KEYS,
            limit=2, after=messages[-1].pk,
        )
        self.assertEqual(delta.items, [])
        self.assertEqual(list(Message.objects.values()), snapshot)
        internal = window(self.records(), keys=MESSAGES_OLDER_KEYS, limit=2)
        self.comment()
        continued = window(self.records(), keys=MESSAGES_OLDER_KEYS, limit=2, after=internal.cursor)
        self.assertEqual([row.pk for row in continued.items], [comments[-3].pk, comments[-4].pk])
        client = TenantAPIClient()
        client.force_authenticate(self.author)
        response = client.get(
            f"/api/v1/organizations/{self.organization.public_id}/conversations/{self.conversation.pk}/messages/?after={messages[-1].pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"], [])

    def test_audience_is_mandatory_and_unknown_values_fail_closed(self):
        with self.assertRaises(TypeError):
            conversation_records(self.conversation)
        for audience in (None, "", "ALL", "unknown"):
            with self.subTest(audience=audience), self.assertRaises(ValueError):
                conversation_records(self.conversation, audience=audience)
        self.assertIs(conversation_messages(self.conversation).model, Message)
        self.assertIs(self.records().model, ConversationComment)

    def test_index_supports_audience_history_order(self):
        self.comment()
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL enable_seqscan = off")
        plan = self.records().order_by("created_at", "id")[:3].explain()
        self.assertIn("conv_comment_window", plan)
