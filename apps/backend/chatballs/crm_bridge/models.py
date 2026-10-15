"""CRM configuration owned by the fork, separate from upstream Contact/Integration."""

from __future__ import annotations

from django.core.validators import RegexValidator
from django.db import models

from chatballs.tenancy.models import TenantRelationModel


class CRMProvider(models.TextChoices):
    NONE = "NONE", "None"
    YCLIENTS = "YCLIENTS", "YCLIENTS"
    DIKIDI = "DIKIDI", "DIKIDI"


class CRMOrganizationConfig(models.Model):
    organization = models.OneToOneField(
        "identity.Organization", on_delete=models.PROTECT, related_name="crm_bridge_config"
    )
    provider = models.CharField(
        max_length=16, choices=CRMProvider.choices, default=CRMProvider.NONE
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(provider__in=["NONE", "YCLIENTS", "DIKIDI"]),
                name="crm_config_valid_provider",
            )
        ]


class CRMCompany(TenantRelationModel):
    name = models.CharField(max_length=160)
    external_company_id = models.CharField(
        max_length=40,
        validators=[RegexValidator(r"^[0-9]+$", "External CRM company ID must be numeric")],
    )
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "external_company_id"),
                name="uniq_crm_company_external_org",
            ),
            models.UniqueConstraint(
                fields=("organization",),
                condition=models.Q(is_primary=True),
                name="uniq_crm_primary_per_org",
            ),
            models.CheckConstraint(
                condition=models.Q(is_primary=False) | models.Q(is_active=True),
                name="crm_primary_must_be_active",
            ),
            models.CheckConstraint(
                condition=models.Q(external_company_id__regex=r"^[0-9]+$"),
                name="crm_external_id_digits_only",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.organization_id}:{self.name} ({self.external_company_id})"


class CRMConnectionBinding(TenantRelationModel):
    tenant_relation_fields = ("integration", "crm_company")

    integration = models.OneToOneField(
        "integrations.Integration", on_delete=models.PROTECT, related_name="crm_bridge_binding"
    )
    crm_company = models.ForeignKey(
        CRMCompany, on_delete=models.PROTECT, related_name="connection_bindings"
    )

    def __str__(self) -> str:
        return f"{self.integration_id} -> {self.crm_company_id}"
