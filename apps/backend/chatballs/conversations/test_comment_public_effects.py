"""A stored comment cannot act as a customer-facing reply."""

from contextlib import ExitStack
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from chatballs.conversations import transports
from chatballs.conversations.comment_test_base import CommentTestBase
from chatballs.conversations.models import (
    ControlMode,
    Conversation,
    ExpectedResponder,
    Message,
    MessageAuthor,
)
from chatballs.conversations.serializers import pending_counts_for
from chatballs.conversations.stats import sales_overview_stats
from chatballs.events.models import OutboxEvent
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.notifications.models import Notification


class CommentPublicEffectsTests(CommentTestBase):
    def test_comment_preserves_waiting_state_statistics_unread_counts_and_delivery(self):
        Message.objects.create(
            conversation=self.conversation, author_type=MessageAuthor.CONTACT, text="Waiting",
        )
        waiting = timezone.now() - timedelta(minutes=30)
        connection = Integration.objects.create(
            organization=self.organization, channel=self.conversation.channel,
            kind=IntegrationKind.MESSENGER, provider=IntegrationProvider.TELEGRAM,
            name="External connection",
        )
        Conversation.objects.filter(pk=self.conversation.pk).update(
            control_mode=ControlMode.PAUSED, expected_responder=ExpectedResponder.OPERATOR,
            waiting_since=waiting, last_activity_at=waiting, assigned_operator=self.author,
            assigned_at=waiting, connection=connection, external_chat_id="customer-chat",
        )
        before = Conversation.objects.filter(pk=self.conversation.pk).values().get()
        stats = sales_overview_stats(self.context, "today")
        events = list(OutboxEvent.objects.values())
        notifications = list(Notification.objects.values())
        pending = pending_counts_for([self.conversation.pk], {})
        self.assertEqual(pending, {self.conversation.pk: 1})
        with ExitStack() as observers:
            # Observe real dispatchers without replacing their responses or
            # providing a fake transport/backend. None may run for a comment.
            sends = [observers.enter_context(patch.object(
                transports, name, wraps=getattr(transports, name),
            )) for name in (
                "send_reply", "send_voice", "send_file", "send_contact_request",
                "send_contact_ack", "send_call_invite",
            )]
            for _ in range(3):
                self.comment()
            for send in sends:
                send.assert_not_called()
        self.assertEqual(Conversation.objects.filter(pk=self.conversation.pk).values().get(), before)
        self.assertEqual(sales_overview_stats(self.context, "today"), stats)
        self.assertEqual(pending_counts_for([self.conversation.pk], {}), pending)
        self.assertEqual(list(OutboxEvent.objects.values()), events)
        self.assertEqual(list(Notification.objects.values()), notifications)
        self.assertEqual(self.conversation.messages.count(), 1)
