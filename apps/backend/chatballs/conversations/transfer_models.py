"""Internal transfer data, separate from messages and AI/customer history."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from chatballs.tenancy.models import TenantRelationModel


class TransferReason(models.Model):
    organization = models.ForeignKey("identity.Organization", on_delete=models.PROTECT)
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"], name="uniq_transfer_reason_org_code"
            ),
        ]

    def __str__(self):
        return f"transfer-reason:{self.organization_id}/{self.code}"


class ConversationTransfer(TenantRelationModel):
    tenant_relation_fields = ("conversation", "reason")
    conversation = models.ForeignKey(
        "conversations.Conversation", on_delete=models.CASCADE, related_name="transfers"
    )
    reason = models.ForeignKey(TransferReason, on_delete=models.PROTECT, related_name="transfers")
    previous_operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    new_operator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    occurred_at = models.DateTimeField(auto_now_add=True)
    operation_id = models.UUIDField()
    reason_code = models.SlugField(max_length=64)
    reason_name = models.CharField(max_length=120)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]
        indexes = [
            models.Index(
                fields=["organization", "conversation", "-occurred_at", "-id"],
                name="transfer_history_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "operation_id"], name="uniq_transfer_org_operation"
            ),
        ]

    def validate_tenant_relations(self):
        from chatballs.identity.models import OrganizationMembership

        super().validate_tenant_relations()
        user_ids = {
            self.previous_operator_id, self.new_operator_id, self.initiated_by_id
        } - {None}
        member_ids = set(OrganizationMembership.objects.filter(
            organization_id=self.organization_id, user_id__in=user_ids
        ).values_list("user_id", flat=True))
        if member_ids != user_ids:
            raise ValidationError("Transfer participants must belong to the organization")

    def __str__(self):
        return f"transfer:{self.organization_id}/{self.operation_id}"
