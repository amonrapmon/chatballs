from django.db import DatabaseError, connection, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from chatballs.ai.assistance_behavior_base import AssistanceBehaviorData
from chatballs.ai.assistance_send import send_suggestion
from chatballs.ai.assistance_send_models import ReplySuggestionSend
from chatballs.conversations.message_views import ConversationMessageView
from chatballs.conversations.models import Conversation, Message
from chatballs.integrations.models import (
    Integration,
    IntegrationKind,
    IntegrationProvider,
)
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic


class AssistanceSendTests(AssistanceBehaviorData, TestCase):
    def post(self, suggestion, key="send", text="Edited employee reply", conversation=None):
        request = APIRequestFactory().post("/", {
            "suggestionId": str(suggestion.public_id), "operationKey": key, "text": text,
        }, format="json")
        request.tenant_context = self.context
        force_authenticate(request, self.member.user)
        return ConversationMessageView.as_view()(request,
            conversation_id=(conversation or self.conversation).pk)

    def test_normal_send_records_source_message_operator_time_and_retry_is_one_message(self):
        suggestion = self.generate(self.request())
        response = self.post(suggestion)
        self.assertEqual(response.status_code, 201)
        receipt = ReplySuggestionSend.objects.get()
        self.assertEqual(receipt.message.text, "Edited employee reply")
        self.assertEqual(receipt.message.author_user_id, self.member.user_id)
        self.assertEqual(receipt.sent_by, self.member)
        self.assertGreaterEqual(receipt.sent_at, receipt.message.created_at)
        source = suggestion.original_text
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.original_text, source)
        self.assertNotEqual(source, receipt.message.text)
        self.assertEqual(self.post(suggestion).data, response.data)
        self.assertEqual(Message.objects.filter(author_type="OPERATOR").count(), 1)
        self.assertEqual(self.conversation.domain_events.filter(event_type="PUBLIC_REPLY", actor_kind="HUMAN").count(), 1)
        self.assertEqual(self.post(suggestion, text="Different reply").status_code, 400)
        self.assertEqual(self.post(suggestion, key="second-send").status_code, 400)

    def test_suggestion_send_claims_assignment_in_human_and_retry_adds_no_facts(self):
        from chatballs.conversations.assignment import assign_operator
        Conversation.objects.filter(pk=self.conversation.pk).update(assigned_operator=None)
        assign_operator(context=self.context, conversation_id=self.conversation.pk,
                        assignee=self.member.user)
        suggestion = self.generate(self.request())
        self.assertEqual(self.post(suggestion).status_code, 201)
        self.assertEqual(self.post(suggestion).status_code, 201)
        self.assertEqual(self.conversation.domain_events.filter(event_type="ACCEPTED").count(), 1)
        self.assertEqual(self.conversation.domain_events.filter(event_type="PUBLIC_REPLY").count(), 1)

    def test_foreign_suggestion_and_revoked_or_closed_reply_are_rejected(self):
        suggestion = self.generate(self.request())
        another = Conversation.objects.create(
            organization=self.organization, channel=self.agent.channel,
            contact=self.conversation.contact, control_mode="HUMAN", assigned_operator=self.member.user,
        )
        self.assertEqual(self.post(suggestion, conversation=another).status_code, 404)
        other, other_member, agent, conversation = self.create_tenant("foreign-send")
        context = TenantContext.for_membership(other_member)
        with self.assertRaises(Exception) as denied:
            send_suggestion(context=context, conversation_id=conversation.pk,
                            suggestion_id=suggestion.public_id, key="foreign", text="No")
        self.assertEqual(denied.exception.status_code, 404)
        self.member.blocked_at = timezone.now()
        self.member.save(update_fields=["blocked_at"])
        self.assertEqual(self.post(suggestion).status_code, 403)
        self.assertFalse(ReplySuggestionSend.objects.exists())

    def test_runtime_rls_and_database_validate_association_and_source_is_immutable(self):
        suggestion = self.generate(self.request())
        with tenant_atomic(self.context):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            send_suggestion(context=self.context, conversation_id=self.conversation.pk,
                            suggestion_id=suggestion.public_id, key="runtime", text="Runtime reply")
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE NONE")
        receipt = ReplySuggestionSend.objects.get()
        with self.assertRaises(DatabaseError), transaction.atomic():
            ReplySuggestionSend.objects.filter(pk=receipt.pk).update(operation_key="overwrite")
        other, _, _, _ = self.create_tenant("rls-send")
        with tenant_atomic(other.pk):
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
            self.assertFalse(ReplySuggestionSend.objects.exists())
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE NONE")

    def test_database_rejects_same_tenant_wrong_conversation_association_and_delete_cleans_history(self):
        from chatballs.conversations.services import delete_conversation

        suggestion = self.generate(self.request())
        other = Conversation.objects.create(
            organization=self.organization, channel=self.agent.channel,
            contact=self.conversation.contact,
        )
        message = Message.objects.create(conversation=other, author_type="OPERATOR",
                                         author_user=self.member.user, text="Wrong dialog")
        with self.assertRaises(DatabaseError), transaction.atomic():
            ReplySuggestionSend.objects.create(
                organization=self.organization, suggestion=suggestion, message=message,
                sent_by=self.member, operation_key="forged",
            )
        self.assertEqual(self.post(suggestion).status_code, 201)
        delete_conversation(context=self.context, conversation=self.conversation)
        self.assertFalse(ReplySuggestionSend.objects.exists())
        self.assertFalse(suggestion.__class__.objects.exists())

    def test_real_web_transport_is_deferred_until_commit_and_not_scheduled_on_retry(self):
        connection = Integration.objects.create(
            organization=self.organization, name="Web", kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.WEB,
        )
        Conversation.objects.filter(pk=self.conversation.pk).update(connection=connection)
        suggestion = self.generate(self.request())
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.assertEqual(self.post(suggestion).status_code, 201)
        deliveries = [callback for callback in callbacks if callback.__name__ == "deliver"]
        self.assertEqual(len(deliveries), 1)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.assertEqual(self.post(suggestion).status_code, 201)
        self.assertEqual(callbacks, [])

    def test_email_delivery_after_commit_uses_runtime_tenant_scope_and_failure_does_not_repeat(self):
        # Real SMTP connection refusal in this container; no substitute mail server.
        connection_record = Integration.objects.create(
            organization=self.organization, name="Email", kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.EMAIL, secret="test-mail-secret",
            config={"smtp_host": "127.0.0.1", "smtp_port": 1,
                    "email": "support@example.test"},
        )
        Conversation.objects.filter(pk=self.conversation.pk).update(
            connection=connection_record, external_chat_id="customer@example.test",
            transport_meta={"subject": "Original thread", "last_message_id": "<incoming@example.test>"},
        )
        suggestion = self.generate(self.request())
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.assertEqual(self.post(suggestion).status_code, 201)
        deliveries = [callback for callback in callbacks if callback.__name__ == "deliver"]
        self.assertEqual(len(deliveries), 1)
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE chatballs_runtime_app")
        try:
            deliveries[0]()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE NONE")
        self.assertEqual(ReplySuggestionSend.objects.count(), 1)
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.assertEqual(self.post(suggestion).status_code, 201)
        self.assertEqual(callbacks, [])
