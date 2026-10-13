"""Append-only internal history, independent of Conversation.note and Message."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from chatballs.conversations.audience import ConversationAudience
from chatballs.i18n import t
from chatballs.tenancy.models import TenantRelationModel


class ConversationComment(TenantRelationModel):
    tenant_relation_fields = ("conversation",)
    # PostgreSQL cascades parent deletion; the app cannot DELETE individual comments.
    conversation = models.ForeignKey(
        "conversations.Conversation", on_delete=models.DO_NOTHING, related_name="comments"
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    # No default: creation must explicitly choose the internal audience.
    audience = models.CharField(max_length=16, choices=[("INTERNAL", "INTERNAL")])
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    operation_id = models.UUIDField()

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["organization", "conversation", "audience", "created_at", "id"],
                name="conv_comment_window",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(audience=ConversationAudience.INTERNAL),
                name="conv_comment_internal_only",
            ),
            models.CheckConstraint(
                condition=models.Q(text__regex=r"\S"), name="conv_comment_text_required",
            ),
            models.UniqueConstraint(
                fields=["organization", "operation_id"], name="uniq_comment_org_operation",
            ),
        ]

    def validate_tenant_relations(self):
        from chatballs.identity.models import OrganizationMembership

        super().validate_tenant_relations()
        if not OrganizationMembership.objects.filter(
            organization_id=self.organization_id, user_id=self.author_id
        ).exists():
            raise ValidationError(t("comments.author_required"))

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(t("comments.append_only"))
        if self.audience != ConversationAudience.INTERNAL:
            raise ValidationError(t("comments.internal_required"))
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValidationError(t("comments.text_required"))
        # A new instance with an existing pk must never overwrite a sent record.
        kwargs["force_insert"] = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"comment:{self.organization_id}/{self.conversation_id}/{self.pk}"
