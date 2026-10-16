"""Durable operation results, with transitions as the interval history.

No-op operations retain their original response but do not start an interval.
"""

from django.db import models
from django.db.models import F, Q

from chatballs.identity.work_status_codes import WorkStatus
from chatballs.tenancy.models import TenantRelationModel


class WorkStatusOperation(TenantRelationModel):
    tenant_relation_fields = ("membership",)
    membership = models.ForeignKey(
        "identity.OrganizationMembership", on_delete=models.PROTECT,
        related_name="work_status_operations",
    )
    operation_id = models.UUIDField()
    previous_status = models.CharField(max_length=16, choices=WorkStatus.choices)
    status = models.CharField(max_length=16, choices=WorkStatus.choices)
    version = models.PositiveBigIntegerField()
    changed_at = models.DateTimeField(null=True)
    recorded_at = models.DateTimeField()
    # A block terminates this selection without changing the selected status.
    stopped_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        ordering = ["version", "id"]
        indexes = [models.Index(fields=["organization", "membership", "version"], name="work_status_history_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(stopped_at__isnull=True) | Q(stopped_at__gte=F("changed_at")), name="work_status_stop_time"),
            models.UniqueConstraint(fields=["membership", "operation_id"], name="uniq_work_status_operation"),
            models.UniqueConstraint(fields=["membership", "version"], condition=~Q(previous_status=F("status")), name="uniq_work_status_transition"),
            models.CheckConstraint(condition=Q(status__in=WorkStatus.values, previous_status__in=WorkStatus.values), name="work_status_operation_valid"),
            models.CheckConstraint(condition=Q(version=0, changed_at__isnull=True, status=WorkStatus.UNAVAILABLE, previous_status=WorkStatus.UNAVAILABLE) | Q(version__gt=0, changed_at__isnull=False), name="work_status_operation_initial"),
            models.CheckConstraint(condition=Q(previous_status=F("status")) | Q(changed_at=F("recorded_at"), version__gt=0), name="work_status_transition_time"),
        ]

    def __str__(self):
        return f"work-status:{self.membership_id}/{self.operation_id}"

    @property
    def changed(self):
        return self.previous_status != self.status
