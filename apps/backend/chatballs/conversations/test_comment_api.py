from uuid import uuid4

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

from chatballs.conversations.comment_models import ConversationComment
from chatballs.conversations.comment_services import MAX_COMMENT_LENGTH, create_comment
from chatballs.conversations.comment_test_base import CommentTestBase
from chatballs.conversations.models import Conversation, Message
from chatballs.conversations.participant_models import ConversationParticipant
from chatballs.events.models import OutboxEvent
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import OrganizationMembership
from chatballs.notifications.models import Notification
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient as APIClient


class CommentAPITests(CommentTestBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(self.author)
        self.url = self.url_for(self.conversation.pk)

    def url_for(self, conversation_id):
        return f"/api/v1/organizations/{self.organization.public_id}/conversations/{conversation_id}/comments/"

    def post(self, **changes):
        return self.client.post(self.url, {
            "audience": "INTERNAL", "text": "Internal discussion",
            "operationId": str(uuid4()), **changes,
        }, format="json")

    def test_requires_explicit_audience_uuid_and_bounded_string(self):
        invalid = (
            {"audience": None}, {"audience": "PUBLIC"}, {"audience": []},
            {"text": None}, {"text": 42}, {"text": " \n\t"},
            {"text": "Invalid\x00text"},
            {"text": "x" * (MAX_COMMENT_LENGTH + 1)},
            {"operationId": None}, {"operationId": "invalid"}, {"operationId": True},
        )
        for changes in invalid:
            with self.subTest(changes=list(changes)):
                self.assertEqual(self.post(**changes).status_code, 400)
        for missing in ("audience", "operationId"):
            data = {"audience": "INTERNAL", "text": "Text", "operationId": str(uuid4())}
            del data[missing]
            self.assertEqual(self.client.post(self.url, data, format="json").status_code, 400)
        self.assertEqual(ConversationComment.objects.count(), 0)
        self.assertEqual(self.client.post(self.url, ["invalid"], format="json").status_code, 400)
        # JSON can contain an escaped unpaired surrogate; reject it before PostgreSQL.
        self.assertEqual(self.client.post(
            self.url,
            '{"audience":"INTERNAL","text":"\\ud800","operationId":"' + str(uuid4()) + '"}',
            content_type="application/json",
        ).status_code, 400)
        self.assertEqual(self.post(text="x" * MAX_COMMENT_LENGTH).status_code, 201)

    def test_author_photo_link_is_scoped_to_the_viewed_organization(self):
        self.assertIsNone(self.post().json()["comment"]["author"]["avatarUrl"])
        self.author.avatar.name = f"users/{self.author.pk}/avatar-photo.png"
        self.author.save(update_fields=["avatar"])
        prefix = f"/api/v1/organizations/{self.organization.public_id}/employees/{self.author.pk}/avatar/?v="
        self.assertTrue(self.post().json()["comment"]["author"]["avatarUrl"].startswith(prefix))
        listed = self.client.get(self.url).json()["items"]
        self.assertEqual(len(listed), 2)
        for item in listed:
            self.assertTrue(item["author"]["avatarUrl"].startswith(prefix))

    def test_replay_preserves_record_and_conflicting_operation_does_not_rewrite(self):
        operation = str(uuid4())
        start = timezone.now()
        created = self.post(operationId=operation, authorId=self.foreign_author.pk, createdAt="2000-01-01")
        self.assertEqual(created.status_code, 201)
        original = created.json()["comment"]
        self.assertEqual(original["author"]["id"], self.author.pk)
        self.assertGreaterEqual(ConversationComment.objects.get().created_at, start)
        repeated = self.post(operationId=operation)
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()["comment"], original)
        self.assertEqual(self.post(operationId=operation, text="Changed").status_code, 409)
        other = self.make_conversation(self.organization, "another")
        self.assertEqual(self.client.post(self.url_for(other.pk), {
            "audience": "INTERNAL", "text": original["text"], "operationId": operation,
        }, format="json").status_code, 409)
        second = OrganizationMembership.objects.create(
            organization=self.organization, user=self.foreign_author, role="ADMIN",
        )
        self.client.force_authenticate(second.user)
        self.assertEqual(self.post(operationId=operation).status_code, 409)
        self.assertEqual(ConversationComment.objects.count(), 1)
        self.assertEqual(self.client.get(self.url).json()["items"], [original])

    def test_paginated_history_and_deltas_are_separate_from_customer_messages(self):
        comments = [self.post(text=f"Comment {index}").json()["comment"] for index in range(5)]
        page = self.client.get(self.url, {"limit": 2}).json()
        self.assertEqual(page["items"], comments[-2:])
        self.assertTrue(page["hasMore"])
        older = self.client.get(self.url, {"limit": 2, "before": page["cursor"]}).json()
        self.assertEqual(older["items"], comments[1:3])
        delta = self.client.get(self.url, {"limit": 2, "after": comments[0]["id"]}).json()
        self.assertEqual(delta["items"], comments[1:3])
        continued = self.client.get(self.url, {"limit": 2, "after": delta["cursor"]}).json()
        self.assertEqual(continued["items"], comments[3:])
        self.assertFalse(continued["hasMore"])
        self.assertEqual(self.client.get(self.url, {"limit": "bad"}).status_code, 400)
        self.assertEqual(self.client.get(self.url, {"before": "-1"}).status_code, 400)
        self.assertEqual(Message.objects.count(), 0)
        messages_url = self.url.replace("/comments/", "/messages/")
        self.assertEqual(self.client.get(messages_url).json()["items"], [])
        for method in (self.client.patch, self.client.delete):
            self.assertEqual(method(self.url, {}, format="json").status_code, 405)

    def test_access_is_tenant_scoped_and_participation_is_temporary(self):
        self.assertEqual(self.client.get(self.url_for(self.foreign_conversation.pk)).status_code, 404)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.post().status_code, 404)
        self.client.force_authenticate(self.author)
        group = EmployeeGroup.objects.create(organization=self.organization, name="Restricted")
        Conversation.objects.filter(pk=self.conversation.pk).update(group=group)
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(role="EMPLOYEE")
        self.assertEqual(self.post().status_code, 404)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        participation = ConversationParticipant.objects.create(
            organization=self.organization, conversation=self.conversation,
            membership=self.membership, joined_by=self.membership, join_reason="Consultation",
        )
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        participation.left_at = timezone.now()
        participation.left_by = self.membership
        participation.leave_reason = "Finished"
        participation.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.post().status_code, 404)
        self.assertEqual(ConversationComment.objects.count(), 1)

    def test_service_refreshes_stale_membership_and_works_with_runtime_rls(self):
        with transaction.atomic(), tenant_atomic(self.context), connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            comment, created = create_comment(
                context=self.context, conversation_id=self.conversation.pk, audience="INTERNAL",
                text="Runtime comment", operation_id=uuid4(),
            )
            self.assertTrue(created)
            self.assertEqual(comment.organization_id, self.organization.pk)
            self.assertEqual(ConversationComment.objects.count(), 1)
            # Roll back this savepoint, including SET LOCAL ROLE, before the next check.
            transaction.set_rollback(True)
        OrganizationMembership.objects.filter(pk=self.membership.pk).update(blocked_at=timezone.now())
        with self.assertRaises(NotFound):
            create_comment(context=self.context, conversation_id=self.conversation.pk,
                           audience="INTERNAL", text="Denied", operation_id=uuid4())

    def test_creation_preserves_conversation_state_and_customer_effects(self):
        before = Conversation.objects.filter(pk=self.conversation.pk).values().get()
        events = list(OutboxEvent.objects.values())
        notifications = list(Notification.objects.values())
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(Conversation.objects.filter(pk=self.conversation.pk).values().get(), before)
        self.assertEqual(list(OutboxEvent.objects.values()), events)
        self.assertEqual(list(Notification.objects.values()), notifications)
        self.assertEqual(Message.objects.count(), 0)
