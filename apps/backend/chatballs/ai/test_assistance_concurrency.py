import time
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from chatballs.ai.assistance_behavior_base import AssistanceBehaviorData
from chatballs.ai.assistance_services import request_suggestion
from chatballs.ai.models import ReplyAssistanceAttempt, ReplySuggestion
from chatballs.conversations.models import Conversation
from chatballs.events.models import OutboxEvent
from chatballs.identity.models import OrganizationMembership
from chatballs.tenancy.database import tenant_atomic


class AssistanceConcurrencyTests(AssistanceBehaviorData, TransactionTestCase):
    def test_concurrent_repeated_request_commits_one_operation_and_one_background_event(self):
        def request():
            close_old_connections()
            try:
                with tenant_atomic(self.context):
                    suggestion = request_suggestion(
                        context=self.context, conversation_id=self.conversation.pk, key="same-key",
                    )
                    return suggestion.public_id
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(request)
            second = executor.submit(request)
            self.assertEqual(first.result(timeout=30), second.result(timeout=30))
        self.assertEqual(ReplyAssistanceAttempt.objects.count(), 1)
        self.assertEqual(ReplySuggestion.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.count(), 1)

    def test_permission_is_reloaded_after_waiting_for_the_conversation_lock(self):
        def request():
            close_old_connections()
            try:
                with tenant_atomic(self.context):
                    with connection.cursor() as cursor:
                        cursor.execute("SET LOCAL application_name = 'assistance-revocation-test'")
                    try:
                        request_suggestion(context=self.context,
                            conversation_id=self.conversation.pk, key="revoked-while-waiting")
                    except PermissionDenied:
                        return "denied"
                    return "allowed"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with tenant_atomic(self.context):
                Conversation.objects.select_for_update().get(pk=self.conversation.pk)
                future = executor.submit(request)
                deadline = time.monotonic() + 10
                waiting = False
                while time.monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_stat_clear_snapshot()")
                        cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                            "WHERE datname=current_database() "
                            "AND application_name='assistance-revocation-test' "
                            "AND wait_event_type='Lock')")
                        waiting = cursor.fetchone()[0]
                    if waiting:
                        break
                    time.sleep(0.01)
                self.assertTrue(waiting)
                OrganizationMembership.objects.filter(pk=self.member.pk).update(blocked_at=timezone.now())
            self.assertEqual(future.result(timeout=20), "denied")
        self.assertFalse(ReplySuggestion.objects.exists())
        self.assertFalse(OutboxEvent.objects.exists())
