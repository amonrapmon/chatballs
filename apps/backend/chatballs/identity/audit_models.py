"""Organization audit records; identity entities are defined in models.py."""

from django.conf import settings
from django.db import models


class AuditResult(models.TextChoices):
    SUCCESS = "SUCCESS", "Success"
    DENIED = "DENIED", "Denied"
    FAILED = "FAILED", "Failed"


class AuditEvent(models.Model):
    organization = models.ForeignKey(
        "identity.Organization",
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="audit_events",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=128)
    object_type = models.CharField(max_length=128, blank=True)
    object_id = models.CharField(max_length=128, blank=True)
    result = models.CharField(max_length=32, choices=AuditResult.choices, default=AuditResult.SUCCESS)
    payload = models.JSONField(default=dict, blank=True)
    correlation_id = models.CharField(max_length=128, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "created_at"]),
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["object_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.action}:{self.result}"
