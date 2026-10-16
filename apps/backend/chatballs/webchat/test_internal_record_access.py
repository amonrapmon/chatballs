"""Public HTTP boundaries use real session resolution and record selectors."""

from rest_framework.test import APIClient

from chatballs.conversations.comment_test_base import CommentTestBase
from chatballs.conversations.models import Message, MessageAuthor, MessageKind
from chatballs.conversations.system_events import OPERATOR_ONLY_EVENTS
from chatballs.webchat.models import WebSession
from chatballs.webchat.testing import create_web_widget


class InternalRecordAccessTests(CommentTestBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        widget = create_web_widget(self.conversation.channel)
        issued = self.client.post(
            "/api/v1/webchat/session/", {"widgetKey": widget.public_key}, format="json",
        )
        self.assertEqual(issued.status_code, 201, issued.content)
        self.token = issued.json()["token"]
        session = WebSession.objects.get(widget=widget)
        self.conversation.contact = session.identity.contact
        self.conversation.connection = widget.integration
        self.conversation.save(update_fields=["contact", "connection"])

    def message(self, **changes):
        return Message.objects.create(
            conversation=self.conversation, author_type=MessageAuthor.CONTACT,
            **changes,
        )

    def history(self, since=0):
        response = self.client.get(
            "/api/v1/webchat/messages/", {"since": since, "token": self.token},
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_full_history_and_delta_exclude_comments_and_operator_only_events(self):
        first = self.message(text="Customer question")
        self.comment(text="Private discussion")
        for event in OPERATOR_ONLY_EVENTS:
            self.message(system_event=event, text="Private event")
        last = self.message(text="Public answer")
        full = self.history()
        self.assertEqual([m["id"] for m in full["messages"]], [first.pk, last.pk])
        delta = self.history(first.pk)
        self.assertFalse(delta["reset"])
        self.assertEqual([m["id"] for m in delta["messages"]], [last.pk])
        self.comment()
        self.assertEqual(self.history(last.pk)["messages"], [])

    def test_hidden_event_cannot_be_used_as_public_delta_anchor(self):
        public = self.message(text="Visible")
        hidden = self.message(system_event=OPERATOR_ONLY_EVENTS[0], text="Hidden")
        result = self.history(hidden.pk)
        self.assertTrue(result["reset"])
        self.assertEqual([m["id"] for m in result["messages"]], [public.pk])

    def test_comment_id_is_not_a_message_id_for_history_or_files(self):
        # Choose a comment key with no public Message counterpart; colliding
        # keys belong to independent tables and may legitimately return Message.
        comment = self.comment(id=900000)
        self.assertTrue(self.history(comment.pk)["reset"])
        self.assertEqual(self.history()["messages"], [])
        for resource in ("audio", "attachment"):
            response = self.client.get(
                f"/api/v1/webchat/messages/{comment.pk}/{resource}/",
                {"token": self.token},
            )
            self.assertEqual(response.status_code, 404)

    def test_direct_links_reject_operator_only_events_and_foreign_records(self):
        for event in OPERATOR_ONLY_EVENTS:
            for kind, resource, field in (
                (MessageKind.VOICE, "audio", "audio"),
                (MessageKind.FILE, "attachment", "attachment"),
            ):
                hidden = self.message(kind=kind, system_event=event, **{field: "private"})
                response = self.client.get(
                    f"/api/v1/webchat/messages/{hidden.pk}/{resource}/",
                    {"token": self.token},
                )
                self.assertEqual(response.status_code, 404)
        foreign = Message.objects.create(
            conversation=self.foreign_conversation, author_type=MessageAuthor.CONTACT,
            kind=MessageKind.FILE, attachment="foreign",
        )
        denied = self.client.get(
            f"/api/v1/webchat/messages/{foreign.pk}/attachment/", {"token": self.token},
        )
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(self.history()["messages"], [])

    def test_matching_comment_and_message_keys_only_resolve_the_public_message(self):
        public = self.message(text="Public record")
        self.comment(id=public.pk, text="Private record with the same key")
        history = self.history()
        self.assertEqual([m["text"] for m in history["messages"]], ["Public record"])
        self.assertFalse(self.history(public.pk)["reset"])
        self.assertEqual(self.history(public.pk)["messages"], [])
