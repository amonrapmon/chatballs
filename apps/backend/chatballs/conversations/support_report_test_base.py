"""Self-contained report tests even after transaction tests flush seed metadata."""

from chatballs.conversations.domain_event_models import ConversationEventHistoryStart
from chatballs.conversations.domain_event_test_base import DomainEventTestBase


class SupportReportTestBase(DomainEventTestBase):
    @classmethod
    def setUpTestData(cls):
        ConversationEventHistoryStart.objects.get_or_create(pk=1)
        super().setUpTestData()
