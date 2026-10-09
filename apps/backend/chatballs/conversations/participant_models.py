"""Temporary membership participation, independent of conversation assignment."""

from django.db import models

from chatballs.tenancy.models import TenantRelationModel


class ConversationParticipantQuerySet(models.QuerySet):
    def active(self):
        return self.filter(left_at__isnull=True)

    def additional(self):
        """Active participants counted against the organization's limit."""
        return self.active().exclude(
            membership__user_id=models.F("conversation__assigned_operator_id")
        )


class ConversationParticipant(TenantRelationModel):
    tenant_relation_fields = ("conversation", "membership", "joined_by", "left_by")
    conversation = models.ForeignKey(
        "conversations.Conversation", on_delete=models.CASCADE, related_name="participants"
    )
    membership = models.ForeignKey(
        "identity.OrganizationMembership", on_delete=models.PROTECT,
        related_name="conversation_participations",
    )
    joined_by = models.ForeignKey(
        "identity.OrganizationMembership", on_delete=models.PROTECT, related_name="+"
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    join_reason = models.TextField()
    left_by = models.ForeignKey(
        "identity.OrganizationMembership", on_delete=models.PROTECT,
        related_name="+", null=True, blank=True,
    )
    left_at = models.DateTimeField(null=True, blank=True)
    leave_reason = models.TextField(blank=True, default="")

    objects = ConversationParticipantQuerySet.as_manager()

    class Meta:
        ordering = ["-joined_at", "-id"]
        indexes = [
            models.Index(
                fields=["organization", "conversation", "-joined_at", "-id"],
                name="participant_history_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["conversation", "membership"],
                condition=models.Q(left_at__isnull=True),
                name="uniq_active_conversation_member",
            ),
            models.CheckConstraint(
                condition=~models.Q(join_reason=""), name="participant_join_reason_required",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(left_at__isnull=True, left_by__isnull=True, leave_reason="")
                    | (models.Q(left_at__isnull=False, left_by__isnull=False)
                       & ~models.Q(leave_reason=""))
                ),
                name="participant_leave_details",
            ),
            models.CheckConstraint(
                condition=models.Q(left_at__isnull=True)
                | models.Q(left_at__gte=models.F("joined_at")),
                name="participant_leave_after_join",
            ),
        ]

    def __str__(self):
        return f"participant:{self.organization_id}/{self.conversation_id}/{self.membership_id}"
