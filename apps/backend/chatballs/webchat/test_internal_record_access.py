"""Public HTTP boundaries use real session resolution and record selectors."""

from pathlib import Path

from django.core.files.base import ContentFile
from rest_framework.test import APIClient

from chatballs.conversations.comment_test_base import CommentTestBase
from chatballs.conversations.models import Message, MessageAuthor, MessageKind
from chatballs.conversations.system_events import OPERATOR_ONLY_EVENTS
from chatballs.identity.models import HumanUser, OrganizationMembership
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

    def avatar(self, message, token=None):
        return self.client.get(
            f"/api/v1/webchat/messages/{message.pk}/author-avatar/",
            {"token": self.token if token is None else token},
        )

    def photo(self, user, filename):
        data = (Path(__file__).parents[1] / "identity/demo_seed/data/media/avatars" / filename).read_bytes()
        user.avatar.save(filename, ContentFile(data), save=False)
        user.avatar_content_type = "image/png"
        user.save(update_fields=["avatar", "avatar_content_type"])
        self.addCleanup(user.avatar.delete, save=False)
        return data

    def test_photos_follow_each_message_author_in_history_and_delta(self):
        colleague = HumanUser.objects.create_user(email="colleague@comments.test", full_name="Colleague")
        OrganizationMembership.objects.create(organization=self.organization, user=colleague, role="EMPLOYEE")
        self.author.full_name = "Assignee"
        self.author.save(update_fields=["full_name"])
        first_photo = self.photo(self.author, "elena-kuznetsova.png")
        second_photo = self.photo(colleague, "anna-kim.png")
        first = Message.objects.create(conversation=self.conversation, author_type=MessageAuthor.OPERATOR, author_user=self.author)
        second = Message.objects.create(conversation=self.conversation, author_type=MessageAuthor.OPERATOR, author_user=colleague)
        self.conversation.assigned_operator = colleague
        self.conversation.save(update_fields=["assigned_operator"])
        full = self.history()["messages"]
        self.assertEqual([(row["authorName"], row["hasAuthorAvatar"]) for row in full], [("Assignee", True), ("Colleague", True)])
        self.assertEqual(self.history(first.pk)["messages"], [full[1]])
        for message, expected in ((first, first_photo), (second, second_photo)):
            response = self.avatar(message)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "image/png")
            self.assertEqual(response["Cache-Control"], "private, no-store")
            self.assertEqual(b"".join(response.streaming_content), expected)
            self.addCleanup(response.close)

    def test_avatar_rejects_invalid_session_hidden_foreign_and_non_operator_records(self):
        self.photo(self.author, "elena-kuznetsova.png")
        public = Message.objects.create(conversation=self.conversation, author_type=MessageAuthor.OPERATOR, author_user=self.author)
        self.assertEqual(self.avatar(public, token="invalid").status_code, 401)
        self.assertEqual(self.avatar(public, token="").status_code, 401)
        hidden = Message.objects.create(conversation=self.conversation, author_type=MessageAuthor.OPERATOR, author_user=self.author, system_event=OPERATOR_ONLY_EVENTS[0])
        foreign = Message.objects.create(conversation=self.foreign_conversation, author_type=MessageAuthor.OPERATOR, author_user=self.foreign_author)
        non_operator = self.message(author_user=self.author)
        self.photo(self.foreign_author, "anna-kim.png")
        for message in (hidden, foreign, non_operator):
            self.assertEqual(self.avatar(message).status_code, 404)
        self.assertNotIn(foreign.pk, [row["id"] for row in self.history()["messages"]])

    def test_operator_without_photo_keeps_name_without_an_avatar_link(self):
        message = Message.objects.create(conversation=self.conversation, author_type=MessageAuthor.OPERATOR, author_user=self.author)
        row = self.history()["messages"][0]
        self.assertEqual(row["authorName"], self.author.full_name)
        self.assertFalse(row["hasAuthorAvatar"])
        self.assertEqual(self.avatar(message).status_code, 404)
