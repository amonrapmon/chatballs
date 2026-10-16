from django.db import connection, transaction

from chatballs.conversations.email_attempt_models import EmailSendAttempt, EmailSendOperation
from chatballs.conversations.email_thread_models import EmailThreadMessage
from chatballs.conversations.email_workflow_test_base import EmailWorkflowTestBase
from chatballs.conversations.models import Conversation, Message, SystemEvent
from chatballs.events.handlers import dispatch
from chatballs.identity.group_models import EmployeeGroupMember
from chatballs.identity.supervision_models import EmployeeGroupSupervision
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


class EmailSendApiTests(EmailWorkflowTestBase):
    def test_atomic_idempotent_mail_and_factual_transport(self):
        before = (self.conversation.channel_id, self.conversation.connection_id, self.conversation.contact_id,
                  self.conversation.group_id, self.conversation.assigned_operator_id)
        first = self.post_send()
        self.assertEqual(first.status_code, 201, first.content)
        second = self.post_send()
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(Message.objects.filter(conversation=self.conversation, author_type="OPERATOR").count(), 1)
        operation = EmailSendOperation.objects.get()
        self.assertEqual(operation.attempts.count(), 1)
        self.assertEqual(operation.letter.connection_id, self.mailbox.pk)
        self.assertTrue(operation.letter.mail_message_id.startswith("<"))
        self.assertEqual(operation.attempts.get().outbox_event.event_type, "conversations.email_send_requested")
        self.assertFalse(first.json()["operation"]["deliveryConfirmed"])
        self.conversation.refresh_from_db()
        self.assertEqual(before, (self.conversation.channel_id, self.conversation.connection_id,
                                 self.conversation.contact_id, self.conversation.group_id, self.conversation.assigned_operator_id))
        fact = self.conversation.domain_events.get()
        self.assertEqual((fact.event_type, fact.actor_kind, fact.transport, fact.connection_id),
                         ("PUBLIC_REPLY", "HUMAN", "EMAIL", self.mailbox.pk))
        self.assertEqual(self.post_send(text="Changed").status_code, 409)

    def test_rejects_unsaved_address_foreign_inactive_and_nonmail_connections(self):
        for values in ({"recipient": "arbitrary@mail-data.test"}, {"connectionId": self.foreign_mailbox.pk},
                       {"connectionId": self.web.pk}, {"connectionId": self.other_mailbox.pk},
                       {"subject": "subject\r\nBcc: hidden@mail-data.test"}):
            with self.subTest(values=values):
                self.assertIn(self.post_send(**values).status_code, (400, 409))
        self.mailbox.is_active = False
        self.mailbox.save()
        self.assertEqual(self.post_send().status_code, 409)
        self.assertFalse(EmailSendOperation.objects.exists())
        self.assertFalse(EmailThreadMessage.objects.exists())

    def test_current_visibility_reply_assignment_and_supervision(self):
        other = self.make_member(self.organization, "other@mail-data.test")
        self.client.force_authenticate(other.user)
        for suffix in ("email/options/", "email/operations/", "visitor-state/"):
            self.assertEqual(self.client.get(self.url(suffix)).status_code, 404)
        self.assertEqual(self.post_send().status_code, 404)
        EmployeeGroupMember.objects.create(employee=other, group=self.group)
        self.assertEqual(self.post_send().status_code, 409)
        self.assertEqual(self.client.get(self.url("email/options/")).status_code, 409)
        other.role = "SUPERVISOR"
        other.save()
        EmployeeGroupMember.objects.filter(employee=other).delete()
        EmployeeGroupSupervision.objects.create(employee=other, group=self.group)
        self.assertEqual(self.client.get(self.url("email/operations/")).status_code, 200)
        self.assertEqual(self.client.get(self.url("email/options/")).status_code, 404)
        self.assertEqual(self.post_send().status_code, 404)

    def test_options_expose_only_saved_addresses_and_safe_mailbox_fields(self):
        response = self.client.get(self.url("email/options/"))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"addresses": [self.contact.email], "mailboxes": [
            {"id": self.mailbox.pk, "name": self.mailbox.name, "address": self.mailbox.config["email"]},
        ]})
        self.assertNotIn(self.mailbox.secret, response.content.decode())

    def test_outbox_rechecks_access_and_connection_without_network(self):
        operation = self.send()
        self.member.blocked_at = self.member.created_at
        self.member.save()
        dispatch(operation.attempts.get().outbox_event)
        attempt = EmailSendAttempt.objects.get()
        self.assertEqual((attempt.state, attempt.error_code), ("FAILED", "CONNECTION_UNAVAILABLE"))
        self.assertIsNone(attempt.started_at)

    def test_runtime_tenant_api_and_foreign_operation_isolation(self):
        operation = self.send()
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            with tenant_atomic(self.context):
                self.assertEqual(self.post_send().status_code, 200)
                self.assertEqual(self.client.get(self.url("email/operations/")).json()["items"][0]["id"], operation.pk)
            with tenant_atomic(TenantContext.for_membership(self.foreign_member)):
                self.assertEqual(EmailSendOperation.objects.count(), 0)
                self.assertEqual(EmailSendAttempt.objects.count(), 0)
        self.client.force_authenticate(self.foreign_member.user)
        self.assertIn(self.client.get(self.url("email/operations/")).status_code, (403, 404))

    def test_closed_request_cannot_send(self):
        Conversation.objects.filter(pk=self.conversation.pk).update(lifecycle="CLOSED")
        self.assertEqual(self.post_send().status_code, 409)
        self.assertFalse(EmailSendOperation.objects.exists())

    def test_first_email_reply_atomically_uses_existing_claim(self):
        EmployeeGroupMember.objects.create(employee=self.member, group=self.group)
        Conversation.objects.filter(pk=self.conversation.pk).update(control_mode="PAUSED", assigned_operator=None)
        response = self.post_send()
        self.assertEqual(response.status_code, 201, response.content)
        self.conversation.refresh_from_db()
        self.assertEqual((self.conversation.control_mode, self.conversation.assigned_operator_id),
                         ("HUMAN", self.member.user_id))
        self.assertEqual(self.conversation.connection_id, self.web.pk)
        self.assertEqual(self.conversation.messages.filter(system_event=SystemEvent.OPERATOR_TOOK).count(), 1)
