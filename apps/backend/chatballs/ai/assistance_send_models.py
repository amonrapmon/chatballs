"""Immutable association of a source proposal with the actual employee reply."""

from django.db import models

from chatballs.tenancy.models import TenantRelationModel


class ReplySuggestionSend(TenantRelationModel):
    tenant_relation_fields = ("suggestion", "message", "sent_by")
    suggestion = models.OneToOneField(
        "ai.ReplySuggestion", on_delete=models.CASCADE, related_name="send",
    )
    message = models.OneToOneField(
        "conversations.Message", on_delete=models.CASCADE, related_name="suggestion_send",
    )
    sent_by = models.ForeignKey(
        "identity.OrganizationMembership", on_delete=models.PROTECT, related_name="+",
    )
    operation_key = models.CharField(max_length=160)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "operation_key"],
                                    name="reply_suggestion_send_operation_uniq"),
            models.CheckConstraint(condition=~models.Q(operation_key=""),
                                   name="reply_suggestion_send_key_present"),
        ]
