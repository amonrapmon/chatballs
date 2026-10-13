"""Participation stays consistent with comments, assistance and domain retries."""

from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import NotFound

from chatballs.ai.assistance_access import may_reply
from chatballs.conversations.assignment import assign_operator
from chatballs.conversations.assignment_policy import AssignmentPolicy
from chatballs.conversations.comment_services import create_comment
from chatballs.conversations.models import ControlMode, Conversation, Message
from chatballs.conversations.participant_services import add_participant, remove_participant
from chatballs.conversations.participant_test_base import ParticipantTestBase
from chatballs.conversations.services import ClaimError, post_operator_message, return_to_queue
from chatballs.conversations.transfer_models import TransferReason
from chatballs.identity.group_models import EmployeeGroup, EmployeeGroupMember
from chatballs.integrations.models import Integration
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient


class ParticipantIntegrationTests(ParticipantTestBase):
    def setUp(self):
        self.group = EmployeeGroup.objects.create(organization=self.organization, name="Private")
        self.conversation.group = self.group
        self.conversation.control_mode = ControlMode.HUMAN
        self.conversation.save(update_fields=["group", "control_mode"])
        self.row, _ = add_participant(
            context=self.context, conversation_id=self.conversation.pk,
            membership_id=self.members[1].pk, reason="Consultation",
        )
        self.participant_context = TenantContext.for_membership(self.members[1])
        self.client = TenantAPIClient()
        self.client.force_authenticate(self.members[1].user)
        self.base = f"/api/v1/conversations/{self.conversation.pk}/"

    def remove(self):
        remove_participant(
            context=self.context, conversation_id=self.conversation.pk,
            participant_id=self.row.pk, reason="Finished",
        )

    def test_comments_and_assistance_follow_current_participation_without_takeover(self):
        body = {"audience": "INTERNAL", "text": "Internal consultation", "operationId": str(uuid4())}
        self.assertEqual(self.client.post(self.base + "comments/", body, format="json").status_code, 201)
        self.assertEqual(len(self.client.get(self.base + "comments/").json()["items"]), 1)
        public = self.client.get(self.base + "messages/").json()
        self.assertNotIn(body["text"], str(public))
        self.assertTrue(may_reply(self.members[1], self.conversation))
        self.conversation.control_mode = ControlMode.AI
        self.conversation.assigned_operator = None
        self.conversation.save(update_fields=["control_mode", "assigned_operator"])
        self.assertFalse(may_reply(self.members[1], self.conversation))
        # Restore the manager before ending participation.
        self.conversation.control_mode = ControlMode.HUMAN
        self.conversation.assigned_operator = self.members[0].user
        self.conversation.save(update_fields=["control_mode", "assigned_operator"])
        self.remove()
        self.assertFalse(may_reply(self.members[1], self.conversation))
        self.assertEqual(self.client.get(self.base + "comments/").status_code, 404)
        with self.assertRaises(NotFound):
            create_comment(context=self.participant_context, conversation_id=self.conversation.pk,
                           audience="INTERNAL", text="Denied", operation_id=uuid4())

    def test_reply_retry_preserves_author_and_facts_but_rechecks_revoked_grant(self):
        operation = uuid4()
        for _ in range(2):
            response = self.client.post(self.base + "messages/", {"text": "Answer"},
                                        format="json", HTTP_IDEMPOTENCY_KEY=str(operation))
            self.assertEqual(response.status_code, 201)
        event = self.conversation.domain_events.get(event_type="PUBLIC_REPLY")
        self.assertEqual(event.initiated_by_id, self.members[1].user_id)
        self.assertEqual(event.responsible_id, self.members[0].user_id)
        self.assertFalse(self.conversation.domain_events.filter(event_type="ACCEPTED").exists())
        link = EmployeeGroupMember.objects.create(
            organization=self.organization, group=self.group, employee=self.members[1],
        )
        self.remove()
        with self.assertRaises(ClaimError):
            post_operator_message(context=self.participant_context, conversation=self.conversation,
                                  text="Answer", operation_id=operation)
        link.delete()
        with self.assertRaises(Conversation.DoesNotExist):
            post_operator_message(context=self.participant_context, conversation=self.conversation,
                                  text="Answer", operation_id=operation)
        self.assertEqual(self.conversation.domain_events.filter(event_type="PUBLIC_REPLY").count(), 1)

    def test_queue_retry_cannot_use_participation_after_independent_access_is_removed(self):
        link = EmployeeGroupMember.objects.create(
            organization=self.organization, group=self.group, employee=self.members[1],
        )
        operation = uuid4()
        return_to_queue(context=self.participant_context, conversation_id=self.conversation.pk,
                        operation_id=operation)
        link.delete()
        with self.assertRaises(ClaimError):
            return_to_queue(context=self.participant_context, conversation_id=self.conversation.pk,
                            operation_id=operation)
        self.assertEqual(self.conversation.domain_events.filter(event_type="QUEUE_ENTERED").count(), 1)

    def test_real_web_media_reply_retries_recheck_participation_and_preserve_responsibility(self):
        integration = Integration.objects.create(
            organization=self.organization, channel=self.conversation.channel,
            name="Web", kind="MESSENGER", provider="WEB",
        )
        self.conversation.connection = integration
        self.conversation.save(update_fields=["connection"])
        operations = []
        messages = []
        try:
            for route, field, name, mime in (
                ("attachments/", "file", "answer.pdf", "application/pdf"),
                ("voice/", "audio", "answer.webm", "audio/webm"),
            ):
                operation = str(uuid4())
                operations.append((route, field, name, mime, operation))
                for _ in range(2):
                    response = self.client.post(
                        self.base + route, {field: SimpleUploadedFile(name, b"content", content_type=mime)},
                        format="multipart", HTTP_IDEMPOTENCY_KEY=operation,
                    )
                    self.assertEqual(response.status_code, 201, response.data)
                message = Message.objects.get(pk=response.data["message"]["id"])
                messages.append(message)
                self.assertEqual(message.author_user_id, self.members[1].user_id)
            self.assertEqual(self.conversation.domain_events.filter(event_type="PUBLIC_REPLY").count(), 2)
            self.assertFalse(self.conversation.domain_events.filter(event_type="ACCEPTED").exists())
            self.conversation.refresh_from_db()
            self.assertEqual(self.conversation.assigned_operator_id, self.members[0].user_id)
            EmployeeGroupMember.objects.create(
                organization=self.organization, group=self.group, employee=self.members[1],
            )
            self.remove()
            for route, field, name, mime, operation in operations:
                response = self.client.post(
                    self.base + route, {field: SimpleUploadedFile(name, b"content", content_type=mime)},
                    format="multipart", HTTP_IDEMPOTENCY_KEY=operation,
                )
                self.assertEqual(response.status_code, 409)
        finally:
            with tenant_atomic(self.context):
                for message in messages:
                    if message.attachment:
                        message.attachment.delete()
                    if message.audio:
                        message.audio.delete()

    def test_transfer_preserves_participant_reply_and_revocation_keeps_new_assignee_access(self):
        policy = AssignmentPolicy.objects.get(organization=self.organization)
        self.assertTrue(policy.ready)
        reason = TransferReason.objects.create(
            organization=self.organization, code="consultation", name="Internal reason",
        )
        data = {"userId": self.members[2].user_id, "reasonId": reason.pk,
                "comment": "Private transfer", "operationId": str(uuid4()), "expectedVersion": 0}
        with self.assertRaises(Conversation.DoesNotExist):
            assign_operator(context=self.participant_context, conversation_id=self.conversation.pk,
                            transfer=data)
        assign_operator(context=self.context, conversation_id=self.conversation.pk, transfer=data)
        message = post_operator_message(context=self.participant_context,
                                        conversation=self.conversation, text="Consultant answer")
        self.assertEqual(message.author_user_id, self.members[1].user_id)
        fact = self.conversation.domain_events.get(event_type="PUBLIC_REPLY")
        self.assertEqual(fact.responsible_id, self.members[2].user_id)
        # The transferred assignee can end participation; the former assignee cannot.
        with self.assertRaises(Conversation.DoesNotExist):
            self.remove()
        self.context = TenantContext.for_membership(self.members[2])
        self.remove()
        self.assertFalse(may_reply(self.members[1], self.conversation))
        self.conversation.refresh_from_db()
        self.assertTrue(may_reply(self.members[2], self.conversation))
        self.assertEqual(self.conversation.assigned_operator_id, self.members[2].user_id)
        self.assertEqual(self.conversation.domain_events.filter(event_type="TRANSFERRED").count(), 1)
