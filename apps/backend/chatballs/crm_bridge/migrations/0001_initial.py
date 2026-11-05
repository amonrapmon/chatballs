"""CRM Bridge v1 owns its schema; no upstream model or migration is modified."""

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("identity", "0042_organization_participant_limit"),
        ("integrations", "0015_merge_gateway_and_external_tools"),
    ]

    operations = [
        migrations.CreateModel(
            name="CRMOrganizationConfig",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("provider", models.CharField(
                    max_length=16, default="NONE",
                    choices=[("NONE", "None"), ("YCLIENTS", "YCLIENTS"), ("DIKIDI", "DIKIDI")],
                )),
                ("organization", models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="crm_bridge_config", to="identity.organization",
                )),
            ],
            options={
                "constraints": [models.CheckConstraint(
                    condition=models.Q(provider__in=["NONE", "YCLIENTS", "DIKIDI"]),
                    name="crm_config_valid_provider",
                )],
            },
        ),
        migrations.CreateModel(
            name="CRMCompany",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=160)),
                ("external_company_id", models.CharField(
                    max_length=40,
                    validators=[django.core.validators.RegexValidator(
                        "^[0-9]+$", "External CRM company ID must be numeric"
                    )],
                )),
                ("is_primary", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="identity.organization",
                )),
            ],
            options={
                "constraints": [
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
                ],
            },
        ),
        migrations.CreateModel(
            name="CRMConnectionBinding",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="+", to="identity.organization",
                )),
                ("crm_company", models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="connection_bindings", to="crm_bridge.crmcompany",
                )),
                ("integration", models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name="crm_bridge_binding", to="integrations.integration",
                )),
            ],
        ),
    ]
