"""Mail operations and factual attempt outcomes, independent of outbox status."""

from django.core.exceptions import ValidationError
from django.db import models

from chatballs.tenancy.models import TenantRelationModel


class EmailSendOperation(TenantRelationModel):
    tenant_relation_fields = ("letter", "initiated_by")
    letter = models.OneToOneField(
        "conversations.EmailThreadMessage", on_delete=models.CASCADE, related_name="send_operation",
    )
    initiated_by = models.ForeignKey("identity.OrganizationMembership", on_delete=models.PROTECT)
    client_key = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["organization", "client_key"], name="uniq_email_operation_client_key"),
            models.CheckConstraint(condition=~models.Q(client_key=""), name="email_operation_key_required"),
        ]

    def validate_tenant_relations(self):
        super().validate_tenant_relations()
        if self.letter.direction != "OUTBOUND":
            raise ValidationError("email_operation_requires_outbound_letter")


class EmailAttemptState(models.TextChoices):
    PENDING = "PENDING"
    SENDING = "SENDING"
    SMTP_ACCEPTED = "SMTP_ACCEPTED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class EmailAttemptError(models.TextChoices):
    """Allowlisted reasons only; raw SMTP errors may contain secrets or PII."""

    NONE = ""
    CONNECTION_UNAVAILABLE = "CONNECTION_UNAVAILABLE"
    SMTP_REJECTED = "SMTP_REJECTED"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    WORKER_INTERRUPTED = "WORKER_INTERRUPTED"


class EmailSendAttempt(TenantRelationModel):
    tenant_relation_fields = ("operation", "initiated_by", "outbox_event")
    operation = models.ForeignKey(EmailSendOperation, on_delete=models.CASCADE, related_name="attempts")
    number = models.PositiveIntegerField()
    initiated_by = models.ForeignKey("identity.OrganizationMembership", on_delete=models.PROTECT)
    outbox_event = models.OneToOneField("events.OutboxEvent", on_delete=models.PROTECT, related_name="email_attempt")
    state = models.CharField(max_length=16, choices=EmailAttemptState.choices, default=EmailAttemptState.PENDING)
    error_code = models.CharField(max_length=32, choices=EmailAttemptError.choices, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["operation_id", "number"]
        constraints = [
            models.UniqueConstraint(fields=["operation", "number"], name="uniq_email_operation_attempt"),
            models.CheckConstraint(condition=models.Q(number__gte=1), name="email_attempt_number_positive"),
            models.CheckConstraint(
                condition=models.Q(error_code__in=EmailAttemptError.values), name="email_attempt_error_safe",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(state="PENDING", started_at__isnull=True, finished_at__isnull=True, error_code="")
                    | models.Q(state="SENDING", started_at__isnull=False, finished_at__isnull=True, error_code="")
                    | models.Q(state="SMTP_ACCEPTED", started_at__isnull=False, finished_at__isnull=False, error_code="")
                    | (models.Q(state="FAILED", finished_at__isnull=False) & ~models.Q(error_code=""))
                    | (models.Q(state="UNKNOWN", started_at__isnull=False, finished_at__isnull=False)
                       & ~models.Q(error_code=""))
                ),
                name="email_attempt_factual_state",
            ),
            models.CheckConstraint(
                condition=models.Q(started_at__isnull=True) | models.Q(started_at__gte=models.F("created_at")),
                name="email_attempt_started_after_create",
            ),
            models.CheckConstraint(
                condition=models.Q(finished_at__isnull=True) | (
                    models.Q(finished_at__gte=models.F("created_at"))
                    & (models.Q(started_at__isnull=True) | models.Q(finished_at__gte=models.F("started_at")))
                ),
                name="email_attempt_finished_after_start",
            ),
        ]

    def validate_tenant_relations(self):
        super().validate_tenant_relations()
        if self.outbox_event.ownership != "TENANT" or self.outbox_event.organization_id != self.organization_id:
            raise ValidationError("email_attempt_requires_tenant_outbox")
