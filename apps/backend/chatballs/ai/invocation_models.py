"""Учёт вызовов LLM."""

from django.db import models

from chatballs.tenancy.models import TenantRelationModel


class LlmInvocationStatus(models.TextChoices):

    SUCCESS = "SUCCESS", "Успех"

    ERROR = "ERROR", "Ошибка"

class LlmInvocation(TenantRelationModel):

    tenant_relation_fields = ("channel",)

    # Учёт по каналу.

    channel = models.ForeignKey("channels.Channel", on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_invocations")

    purpose = models.CharField(max_length=64)

    operation = models.CharField(max_length=16)  # chat | embedding

    model = models.CharField(max_length=128, blank=True)

    prompt_tokens = models.PositiveIntegerField(default=0)

    completion_tokens = models.PositiveIntegerField(default=0)

    total_tokens = models.PositiveIntegerField(default=0)

    latency_ms = models.PositiveIntegerField(default=0)

    status = models.CharField(max_length=16, choices=LlmInvocationStatus.choices, default=LlmInvocationStatus.SUCCESS)

    error = models.TextField(blank=True)

    used_fragment_ids = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:

        ordering = ["-created_at"]

        indexes = [models.Index(fields=["channel", "created_at"])]

    def __str__(self) -> str:

        return f"llm:{self.channel_id}/{self.operation}/{self.status}"
