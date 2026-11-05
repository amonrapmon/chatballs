"""Durable native reply receipts and per-conversation revision.

These models are inert until an ENABLED adapter invokes the persistence service.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from chatballs.tenancy.models import TenantRelationModel


class NativeMirrorConversationState(TenantRelationModel):
    tenant_relation_fields = ("conversation",)

    conversation = models.OneToOneField(
        "conversations.Conversation", on_delete=models.CASCADE,
        related_name="native_mirror_state",
    )
    revision = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"native-state:{self.conversation_id}/revision-{self.revision}"


class MirrorReceiptStatus(models.TextChoices):
    PENDING = "PENDING", "Awaiting conversation"
    STORED = "STORED", "Stored in conversation"
    SELF_ECHO = "SELF_ECHO", "Known own outbound"
    UNCLASSIFIED = "UNCLASSIFIED", "Unknown external origin"


class NativeMirrorReceipt(TenantRelationModel):
    """One provider message per integration/chat, even after event redelivery.

    Text lives here only while awaiting a conversation. Successful storage
    moves it into the canonical Message and clears this staging copy.
    """

    tenant_relation_fields = ("integration", "conversation", "message")

    integration = models.ForeignKey(
        "integrations.Integration", on_delete=models.PROTECT,
        related_name="native_mirror_receipts",
    )
    conversation = models.ForeignKey(
        "conversations.Conversation", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="native_mirror_receipts",
    )
    message = models.OneToOneField(
        "conversations.Message", null=True, blank=True,
        on_delete=models.PROTECT, related_name="+",
    )
    author_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    provider = models.CharField(max_length=32)
    source_id = models.CharField(max_length=128)
    event_id = models.CharField(max_length=256)
    external_chat_id = models.CharField(max_length=128)
    external_message_id = models.CharField(max_length=128)
    payload_hash = models.CharField(max_length=64)
    occurred_at = models.DateTimeField()
    external_reply_to_id = models.CharField(max_length=128, blank=True)
    pending_text = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=MirrorReceiptStatus.choices,
        default=MirrorReceiptStatus.PENDING,
    )
    reason = models.CharField(max_length=48, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("integration", "event_id"),
                name="native_mirror_unique_event",
            ),
            models.UniqueConstraint(
                fields=("integration", "external_chat_id", "external_message_id"),
                name="native_mirror_unique_provider_message",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status=MirrorReceiptStatus.STORED)
                    | models.Q(message__isnull=False, conversation__isnull=False)
                ),
                name="native_mirror_stored_has_message",
            ),
        ]
        indexes = [
            models.Index(
                fields=("organization", "status", "received_at"),
                name="native_mirror_pending_idx",
            ),
            models.Index(
                fields=("organization", "status", "next_attempt_at"),
                name="native_mirror_due_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"native-receipt:{self.pk}"

class PublicationStatus(models.TextChoices):
    QUEUED = "QUEUED", "Awaiting dispatch claim"
    CLAIMED = "CLAIMED", "Dispatch attempted or may have started"
    SUPPRESSED = "SUPPRESSED", "Cancelled before dispatch claim"


class NativeMirrorPublication(TenantRelationModel):
    """Durable first-send boundary for a Gateway AI message.

    A CLAIMED command may already have reached the network, even when an
    HTTP timeout prevents an acknowledgment. Retries must keep its command ID
    and must never reclassify it as suppressible.
    """

    tenant_relation_fields = ("message",)

    message = models.OneToOneField(
        "conversations.Message", on_delete=models.PROTECT,
        related_name="native_mirror_publication",
    )
    revision = models.PositiveBigIntegerField()
    status = models.CharField(
        max_length=16, choices=PublicationStatus.choices,
        default=PublicationStatus.QUEUED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    suppressed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"native-publication:{self.message_id}/{self.status}"
