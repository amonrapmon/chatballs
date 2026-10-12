from dataclasses import replace
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.domain_event_test_base import DomainEventTestBase
from chatballs.conversations.domain_events import record_public_reply
from chatballs.conversations.ingest import ingest_inbound
from chatballs.conversations.maintenance import close_stale_conversations
from chatballs.conversations.models import Conversation, Message
from chatballs.conversations.services import (
    assign_operator,
    claim_conversation,
    close_conversation,
    post_operator_message,
    return_to_queue,
)
from chatballs.conversations.transports.base import InboundMessage
from chatballs.identity.models import HumanUser, OrganizationMembership
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic
from chatballs.testing import TenantAPIClient


class DomainEventSourceTests(DomainEventTestBase):
    def facts(self):
        return ConversationEvent.objects.filter(conversation=self.conversation)

    def test_assignment_claim_queue_close_and_retries(self):
        self.conversation.assigned_operator = None
        self.conversation.save(update_fields=["assigned_operator"])
        return_to_queue(context=self.context, conversation_id=self.conversation.pk)
        operation = uuid4()
        assign_operator(context=self.context, conversation_id=self.conversation.pk,
                        assignee=self.user, operation_id=operation)
        assign_operator(context=self.context, conversation_id=self.conversation.pk,
                        assignee=self.user, operation_id=operation)
        self.assertFalse(self.facts().filter(event_type="ACCEPTED").exists())
        claim = uuid4()
        for _ in range(2):
            claim_conversation(context=self.context, conversation_id=self.conversation.pk,
                               operation_id=claim)
        claim_conversation(context=self.context, conversation_id=self.conversation.pk)
        close = uuid4()
        for _ in range(2):
            close_conversation(context=self.context, conversation_id=self.conversation.pk,
                               operation_id=close)
        self.assertEqual(list(self.facts().values_list("event_type", flat=True)),
                         ["QUEUE_ENTERED", "ASSIGNED", "QUEUE_EXITED", "ACCEPTED", "CLOSED"])
        event = self.facts().get(event_type="CLOSED")
        self.assertEqual(event.responsible_id, self.user.pk)
        self.assertEqual(event.initiated_by_id, self.user.pk)
        self.assertEqual(event.transport, "WEB")
        self.assertEqual(event.connection_id, self.connection.pk)
        self.assertEqual(event.group_id, self.group.pk)

    def test_public_web_reply_retry_and_transaction_rollback(self):
        claim_conversation(context=self.context, conversation_id=self.conversation.pk)
        operation = uuid4()
        first = post_operator_message(context=self.context, conversation=self.conversation,
                                      text="Answer", operation_id=operation)
        second = post_operator_message(context=self.context, conversation=self.conversation,
                                       text="Answer", operation_id=operation)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(self.facts().filter(event_type="PUBLIC_REPLY").count(), 1)
        with self.assertRaises(ValidationError):
            post_operator_message(context=self.context, conversation=self.conversation,
                                  text="Different", operation_id=operation)
        baseline = self.facts().count()
        with self.assertRaises(RuntimeError), transaction.atomic():
            return_to_queue(context=self.context, conversation_id=self.conversation.pk)
            raise RuntimeError("abort domain operation")
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.control_mode, "HUMAN")
        self.assertEqual(self.facts().count(), baseline)

    def test_reused_operation_cannot_target_another_conversation(self):
        operation = uuid4()
        claim_conversation(context=self.context, conversation_id=self.conversation.pk,
                           operation_id=operation)
        other = Conversation.objects.create(
            organization=self.organization, channel=self.conversation.channel,
            contact=self.conversation.contact, connection=self.connection,
        )
        with self.assertRaises(ValidationError):
            claim_conversation(context=self.context, conversation_id=other.pk,
                               operation_id=operation)
        other.refresh_from_db()
        self.assertEqual(other.control_mode, "AI")
        with self.assertRaises(Conversation.DoesNotExist):
            close_conversation(context=self.context, conversation_id=self.foreign_conversation.pk)

    def test_transfer_and_historical_snapshots(self):
        claim_conversation(context=self.context, conversation_id=self.conversation.pk)
        other = HumanUser.objects.create_user(email="replacement@facts.test")
        OrganizationMembership.objects.create(organization=self.organization, user=other, role="EMPLOYEE")
        assign_operator(context=self.context, conversation_id=self.conversation.pk, assignee=other)
        event = self.facts().get(event_type="TRANSFERRED")
        self.assertEqual(event.responsible_id, other.pk)
        replacement_context = TenantContext.for_membership(
            OrganizationMembership.objects.get(organization=self.organization, user=other)
        )
        claim_conversation(context=replacement_context, conversation_id=self.conversation.pk)
        self.assertEqual(self.facts().filter(event_type="ACCEPTED", responsible_id=other.pk).count(), 1)
        self.assertEqual(self.facts().filter(event_type="ACCEPTED").count(), 2)
        self.conversation.group = None
        self.conversation.connection = None
        self.conversation.save(update_fields=["group", "connection"])
        event.refresh_from_db()
        self.assertEqual(event.group_id, self.group.pk)
        self.assertEqual(event.transport, "WEB")

    def test_inbound_queue_followup_and_dedup(self):
        self.connection.channel = self.conversation.channel
        self.connection.save(update_fields=["channel"])
        inbound = InboundMessage(external_id="source-1", user_id="client", chat_id="client",
                                 text="Question", display_name="Client")
        ingest_inbound(self.connection, inbound)
        ingest_inbound(self.connection, inbound)
        current = Conversation.objects.exclude(pk=self.conversation.pk).get(
            organization=self.organization)
        self.assertEqual(current.domain_events.filter(event_type="QUEUE_ENTERED").count(), 1)
        close_conversation(context=self.context, conversation_id=current.pk)
        inbound = replace(inbound, external_id="source-2")
        ingest_inbound(self.connection, inbound)
        following = Conversation.objects.get(previous_conversation=current)
        self.assertEqual(list(following.domain_events.values_list("event_type", flat=True)),
                         ["FOLLOW_UP", "QUEUE_ENTERED"])

    def test_ai_reply_is_separate_and_writer_is_idempotent(self):
        message = Message.objects.create(conversation=self.conversation, author_type="AI", text="AI")
        record_public_reply(message)
        record_public_reply(message)
        event = self.facts().get()
        self.assertEqual(event.actor_kind, "AI")
        self.assertIsNone(event.initiated_by_id)
        self.assertFalse(self.facts().filter(event_type="ACCEPTED").exists())

    def test_http_first_reply_claim_and_retry(self):
        client = TenantAPIClient()
        client.force_authenticate(self.user)
        operation = str(uuid4())
        url = f"/api/v1/conversations/{self.conversation.pk}/messages/"
        for _ in range(2):
            response = client.post(url, {"text": "Public"}, format="json",
                                   HTTP_IDEMPOTENCY_KEY=operation)
            self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.facts().filter(event_type="ACCEPTED").count(), 1)
        self.assertEqual(self.facts().filter(event_type="PUBLIC_REPLY").count(), 1)

    def test_background_close_is_system_and_no_duplicate(self):
        from datetime import timedelta
        self.conversation.last_activity_at = timezone.now() - timedelta(days=8)
        self.conversation.save(update_fields=["last_activity_at"])
        context = TenantContext.for_resource(self.organization)
        self.assertEqual(close_stale_conversations(context), 1)
        self.assertEqual(close_stale_conversations(context), 0)
        event = self.facts().get(event_type="CLOSED")
        self.assertEqual(event.actor_kind, "SYSTEM")
        self.assertEqual(event.responsible_id, self.user.pk)

    def test_services_run_under_runtime_tenant_role(self):
        from django.db import connection
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            claim_conversation(context=self.context, conversation_id=self.conversation.pk)
            with self.assertRaises(Conversation.DoesNotExist):
                close_conversation(context=self.context, conversation_id=self.foreign_conversation.pk)
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE NONE")
        self.assertTrue(self.facts().filter(event_type="ACCEPTED").exists())

    def test_web_file_and_voice_public_replies_are_retry_safe(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        client = TenantAPIClient()
        client.force_authenticate(self.user)
        for route, field, filename, content_type in (
            ("attachments", "file", "answer.pdf", "application/pdf"),
            ("voice", "audio", "answer.webm", "audio/webm"),
        ):
            operation = str(uuid4())
            url = f"/api/v1/conversations/{self.conversation.pk}/{route}/"
            responses = []
            for _ in range(2):
                response = client.post(
                    url, {field: SimpleUploadedFile(filename, b"content", content_type=content_type)},
                    format="multipart", HTTP_IDEMPOTENCY_KEY=operation,
                )
                self.assertEqual(response.status_code, 201, response.data)
                responses.append(response.data["message"]["id"])
            self.assertEqual(responses[0], responses[1])
            message = Message.objects.get(pk=responses[0])
            # Test media is removed through the same FileField API, never shared data.
            with tenant_atomic(self.context):
                if message.audio:
                    message.audio.delete()
                if message.attachment:
                    message.attachment.delete()
        self.assertEqual(self.facts().filter(event_type="ACCEPTED").count(), 1)
        self.assertEqual(self.facts().filter(event_type="PUBLIC_REPLY").count(), 2)

    def test_fact_uses_current_responsibility_and_actual_inbound_transport(self):
        from chatballs.conversations.domain_events import record_queue_entry
        from chatballs.integrations.models import Integration
        actual = Integration.objects.create(
            organization=self.organization, kind="MESSENGER", provider="EMAIL", name="Mail",
        )
        # An AI turn may hold an older in-memory copy while assignment changes.
        message = Message.objects.create(conversation=self.conversation, author_type="AI", text="AI")
        Conversation.objects.filter(pk=self.conversation.pk).update(assigned_operator=None, group=None)
        event = record_public_reply(message)
        self.assertIsNone(event.responsible_id)
        self.assertIsNone(event.group_id)
        record_queue_entry(self.conversation, entered=True, connection=actual)
        incoming = self.facts().get(event_type="QUEUE_ENTERED")
        self.assertEqual(incoming.transport, "EMAIL")
        self.assertEqual(incoming.connection_id, actual.pk)

    def test_old_human_reply_does_not_invent_acceptance(self):
        self.conversation.control_mode = "HUMAN"
        self.conversation.save(update_fields=["control_mode"])
        client = TenantAPIClient()
        client.force_authenticate(self.user)
        response = client.post(f"/api/v1/conversations/{self.conversation.pk}/messages/",
                               {"text": "Answer"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(list(self.facts().values_list("event_type", flat=True)), ["PUBLIC_REPLY"])
