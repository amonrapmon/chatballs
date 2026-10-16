"""Organization skill configuration and explicit agent assignments."""

import uuid

from django.conf import settings
from django.db import models

from chatballs.tenancy.models import TenantRelationModel


class Skill(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    organization = models.ForeignKey("identity.Organization", on_delete=models.PROTECT)
    name = models.CharField(max_length=60)
    description = models.CharField(max_length=200)
    instruction = models.TextField()
    templates = models.JSONField(default=list)
    revision = models.PositiveBigIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "public_id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(revision__gte=1), name="skill_positive_revision"),
            models.CheckConstraint(condition=~models.Q(name=""), name="skill_name_nonempty"),
            models.CheckConstraint(condition=~models.Q(description=""), name="skill_description_nonempty"),
            models.CheckConstraint(condition=~models.Q(instruction=""), name="skill_instruction_nonempty"),
        ]

    def __str__(self):
        return f"skill:{self.public_id}"


class AgentSkill(TenantRelationModel):
    tenant_relation_fields = ("skill", "agent")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="assignments")
    agent = models.ForeignKey("ai.AIAgent", on_delete=models.CASCADE, related_name="skill_assignments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["skill", "agent"], name="unique_agent_skill")]


class SkillRequest(models.Model):
    """Durable request identity; survives deletion without retaining content."""

    organization = models.ForeignKey("identity.Organization", on_delete=models.PROTECT)
    key = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    skill_public_id = models.UUIDField()
    result_revision = models.PositiveBigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["organization", "key"], name="unique_skill_request")]

    def __str__(self):
        return f"skill-request:{self.pk}"
