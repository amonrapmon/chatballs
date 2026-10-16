"""Shared setup for focused tests on the real PostgreSQL test database."""

from uuid import uuid4

from django.core.cache import cache

from chatballs.conversations.domain_event_test_base import DomainEventTestBase
from chatballs.conversations.models import ConnectionIdentity
from chatballs.ratings.models import RatingRequest, RatingSettings
from chatballs.webchat.models import WebChatWidget, WebSession


class RatingTestBase(DomainEventTestBase):
    def setUp(self):
        cache.clear()
        self.connection.channel = self.conversation.channel
        self.connection.status = "OK"
        self.connection.save()
        self.widget = WebChatWidget.objects.create(
            organization=self.organization, integration=self.connection,
            code="ratings", name="Ratings", status="PUBLISHED",
        )
        self.identity = ConnectionIdentity.objects.create(
            organization=self.organization, connection=self.connection,
            contact=self.conversation.contact, external_user_id="rating-client",
        )
        self.session = WebSession.objects.create(
            organization=self.organization, connection=self.connection, widget=self.widget,
            identity=self.identity, token_hash="a" * 64,
        )
        self.conversation.transport_meta = {"webChatWidgetId": self.widget.pk}
        self.conversation.save()
        self.scale = [{"value": value, "label": str(value)} for value in range(1, 6)]
        self.policy = RatingSettings.objects.create(
            organization=self.organization, enabled=True, scale=self.scale,
            text="Test customer question", delay_seconds=0,
        )

    def completion(self, conversation=None):
        conversation = conversation or self.conversation
        conversation.lifecycle = "CLOSED"
        conversation.save(update_fields=["lifecycle"])
        event = self.row(
            conversation_id=conversation.pk, event_type="CLOSED", operation_id=uuid4(),
        )
        event.save()
        return event

    def scheduled(self):
        event = self.completion()
        return RatingRequest.objects.get(completion=event)
