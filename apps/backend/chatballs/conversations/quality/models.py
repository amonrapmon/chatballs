from django.db import models

from chatballs.tenancy.models import TenantRelationModel


class QualityCriteriaVersion(TenantRelationModel):
    tenant_relation_fields = ("created_by",)
    version = models.PositiveIntegerField()
    criteria = models.JSONField()
    created_by = models.ForeignKey("identity.OrganizationMembership", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "conversations"
        constraints = [
            models.UniqueConstraint(fields=["organization", "version"], name="quality_criteria_version"),
            models.CheckConstraint(condition=models.Q(version__gt=0), name="quality_criteria_positive"),
        ]


class QualitySettings(TenantRelationModel):
    tenant_relation_fields = ("current_version",)
    organization = models.OneToOneField("identity.Organization", on_delete=models.PROTECT)
    enabled = models.BooleanField(default=False)
    current_version = models.ForeignKey(QualityCriteriaVersion, on_delete=models.PROTECT, null=True)

    class Meta:
        app_label = "conversations"
        constraints = [models.CheckConstraint(
            condition=models.Q(enabled=False) | models.Q(current_version__isnull=False),
            name="quality_enabled_requires_criteria",
        )]


class QualityJobState(models.TextChoices):
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class QualityJob(TenantRelationModel):
    tenant_relation_fields = ("conversation", "criteria_version")
    # SQL cascades the immutable subtree only after its conversation is gone.
    conversation = models.ForeignKey("conversations.Conversation", on_delete=models.DO_NOTHING)
    # Supplied by the completion journal integration in B18.2, never inferred
    # from last_activity_at. Reopened/closed again means a different event.
    completion_event_id = models.UUIDField()
    completed_at = models.DateTimeField()
    criteria_version = models.ForeignKey(QualityCriteriaVersion, on_delete=models.PROTECT)
    history_revision = models.CharField(max_length=64)
    history_snapshot = models.JSONField()
    revision = models.PositiveIntegerField()
    operation_id = models.UUIDField()
    state = models.CharField(max_length=16, choices=QualityJobState.choices, default=QualityJobState.WAITING)
    error_code = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        app_label = "conversations"
        indexes = [models.Index(fields=["organization", "state", "created_at"], name="quality_job_queue")]
        constraints = [
            models.UniqueConstraint(fields=["organization", "operation_id"], name="quality_job_operation"),
            models.UniqueConstraint(fields=["conversation", "completion_event_id", "revision"], name="quality_job_revision"),
            models.CheckConstraint(condition=models.Q(revision__gt=0), name="quality_job_positive"),
            models.CheckConstraint(condition=models.Q(state__in=QualityJobState.values), name="quality_job_state"),
            models.CheckConstraint(condition=(
                models.Q(state="WAITING", started_at__isnull=True, finished_at__isnull=True, error_code="")
                | models.Q(state="RUNNING", started_at__isnull=False, finished_at__isnull=True, error_code="")
                | models.Q(state="SUCCEEDED", started_at__isnull=False, finished_at__isnull=False, error_code="")
                | (models.Q(state="FAILED", started_at__isnull=False, finished_at__isnull=False) & ~models.Q(error_code=""))
            ), name="quality_job_state_details"),
            models.CheckConstraint(condition=models.Q(finished_at__isnull=True)
                | models.Q(finished_at__gte=models.F("started_at")), name="quality_job_time_order"),
        ]


class QualityResult(TenantRelationModel):
    tenant_relation_fields = ("job",)
    job = models.OneToOneField(QualityJob, on_delete=models.PROTECT, related_name="result")
    # Validated provider output is supplied by B18.2. No provider is called here.
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "conversations"


class QualityJobOperation(TenantRelationModel):
    """Redelivery aliases remain bound to the original snapshot."""
    tenant_relation_fields = ("job",)
    operation_id = models.UUIDField()
    job = models.ForeignKey(QualityJob, on_delete=models.PROTECT)

    class Meta:
        app_label = "conversations"
        constraints = [models.UniqueConstraint(
            fields=["organization", "operation_id"], name="quality_operation_alias",
        )]


class QualityCorrection(TenantRelationModel):
    tenant_relation_fields = ("result", "author")
    result = models.ForeignKey(QualityResult, on_delete=models.PROTECT, related_name="corrections")
    revision = models.PositiveIntegerField()
    criterion_code = models.SlugField(max_length=64)
    value = models.JSONField()
    author = models.ForeignKey("identity.OrganizationMembership", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    reason = models.TextField()

    class Meta:
        app_label = "conversations"
        ordering = ["revision"]
        constraints = [
            models.UniqueConstraint(fields=["result", "revision"], name="quality_correction_revision"),
            models.CheckConstraint(condition=models.Q(revision__gt=0), name="quality_correction_positive"),
            models.CheckConstraint(condition=~models.Q(reason=""), name="quality_correction_reason"),
        ]
