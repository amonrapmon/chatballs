"""One snapshot per CLOSED fact; no retroactive requests on enable."""

from datetime import timedelta

from django.db.models.signals import post_save
from django.dispatch import receiver
from rest_framework.exceptions import ValidationError

from chatballs.conversations.domain_event_models import ConversationEvent
from chatballs.conversations.models import Message
from chatballs.ratings.models import RatingRequest, RatingSettings
from chatballs.ratings.validation import validate_settings
from chatballs.tenancy.database import tenant_atomic
from chatballs.webchat.models import WebSession


def schedule_request(completion):
    with tenant_atomic(completion.organization_id):
        # Settings are always locked before the request, including disabling.
        policy = RatingSettings.objects.select_for_update().filter(
            organization_id=completion.organization_id, enabled=True,
        ).first()
        if policy is None or completion.event_type != "CLOSED":
            return None
        try:
            validate_settings(policy)
        except ValidationError:
            return None
        conversation = completion.conversation
        session = WebSession.objects.filter(
            organization_id=completion.organization_id,
            connection_id=conversation.connection_id,
            connection__provider="WEB", identity__contact_id=conversation.contact_id,
            widget_id=(conversation.transport_meta or {}).get("webChatWidgetId"),
        ).order_by("pk").first()
        request = RatingRequest.objects.get_or_create(
            completion=completion,
            defaults={
                "organization_id": completion.organization_id, "conversation": conversation,
                "scale": policy.scale, "text": policy.text, "delay_seconds": policy.delay_seconds,
                "due_at": completion.occurred_at + timedelta(seconds=policy.delay_seconds),
                "delivery_session_id": session.pk if session else None,
            },
        )[0]
        request.refresh_from_db()
        return request


@receiver(post_save, sender=ConversationEvent, dispatch_uid="ratings.completion")
def completion_saved(sender, instance, created, **kwargs):
    if created and instance.event_type == "CLOSED":
        schedule_request(instance)


@receiver(post_save, sender=Message, dispatch_uid="ratings.customer_followup")
def customer_message_saved(sender, instance, created, **kwargs):
    if not created or instance.author_type != "CONTACT":
        return
    conversation = instance.conversation
    if not conversation.contact_id or not conversation.connection_id:
        return
    with tenant_atomic(conversation.organization_id):
        # The same lock order as delivery; sent requests remain immutable.
        RatingSettings.objects.select_for_update().filter(
            organization_id=conversation.organization_id,
        ).first()
        RatingRequest.objects.filter(
            organization_id=conversation.organization_id,
            conversation__contact_id=conversation.contact_id,
            conversation__connection_id=conversation.connection_id,
            conversation__transport_meta__webChatWidgetId=(conversation.transport_meta or {}).get("webChatWidgetId"),
            completion__occurred_at__lt=instance.created_at,
            sent_at__isnull=True, cancelled_at__isnull=True,
        ).update(cancelled_at=instance.created_at)
