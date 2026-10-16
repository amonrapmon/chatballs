from django.utils import timezone

from chatballs.conversations.email_workflow_test_base import EmailWorkflowTestBase
from chatballs.conversations.models import ConversationParticipant
from chatballs.events.handlers import dispatch


class EmailMergedPermissionTests(EmailWorkflowTestBase):
    def test_active_specialist_can_reply_without_reassigning_and_removal_blocks_outbox(self):
        specialist = self.make_member(self.organization, "specialist@mail-data.test")
        participant = ConversationParticipant.objects.create(
            conversation=self.conversation, membership=specialist, joined_by=self.member,
            join_reason="Specialist help",
        )
        self.client.force_authenticate(specialist.user)
        response = self.post_send()
        self.assertEqual(response.status_code, 201, response.content)
        from chatballs.conversations.email_attempt_models import EmailSendOperation

        operation = EmailSendOperation.objects.get(pk=response.json()["operation"]["id"])
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.member.user_id)
        participant.left_at, participant.left_by, participant.leave_reason = timezone.now(), self.member, "Completed"
        participant.save()
        self.assertEqual(self.client.get(self.url("email/operations/")).status_code, 404)
        dispatch(operation.attempts.get().outbox_event)
        self.assertEqual(operation.attempts.get().state, "FAILED")

    def test_pending_assignment_is_accepted_once_on_first_mail_reply(self):
        from uuid import uuid4

        from chatballs.conversations.domain_events import record_fact

        record_fact(self.conversation, "ASSIGNED", operation_id=uuid4(), actor_kind="SYSTEM")
        first, second = self.post_send(), self.post_send()
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(self.conversation.domain_events.filter(event_type="ACCEPTED").count(), 1)
        self.assertEqual(self.conversation.domain_events.filter(event_type="PUBLIC_REPLY", transport="EMAIL").count(), 1)
