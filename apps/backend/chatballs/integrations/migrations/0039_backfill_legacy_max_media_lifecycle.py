"""Repair legacy MAX staged-media grant without reprovisioning credentials.

New provisioning already enables connectorMediaLifecycleEnabled. Older MAX
Integrations may have inbound media enabled but lack this grant, while the
registered MAX adapter already announces staged media. The mismatch produces
HTTP 422 on imageMessage/documentMessage before any file download.

Only infer the legacy missing/null grant for a first-party MAX Connector with
media inbound already explicitly enabled. Preserve explicit False, other
providers, all secrets and all existing configuration fields.
"""
from django.db import migrations


def repaired_config(config):
    if not isinstance(config, dict):
        return None
    if config.get("connector_service") != "green_api_max":
        return None
    if config.get("connectorMediaInboundEnabled") is not True:
        return None
    if config.get("connectorMediaLifecycleEnabled") is not None:
        return None
    return {**config, "connectorMediaLifecycleEnabled": True}


def backfill_legacy_max_lifecycle(apps, schema_editor):
    from chatballs.tenancy.database import tenant_atomic
    from chatballs.tenancy.ingress import organization_ids

    Integration = apps.get_model("integrations", "Integration")
    alias = schema_editor.connection.alias
    # Integration is RLS-scoped. Never scan or update it outside a tenant.
    for organization_id in organization_ids():
        with tenant_atomic(organization_id, using=alias):
            integrations = Integration.objects.using(alias).filter(
                organization_id=organization_id,
                provider="API_CONNECTOR",
                config__connector_service="green_api_max",
            )
            for integration in integrations.iterator(chunk_size=100):
                config = repaired_config(integration.config)
                if config is not None:
                    Integration.objects.using(alias).filter(
                        pk=integration.pk,
                        organization_id=organization_id,
                    ).update(config=config)


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0038_merge_upstream_122"),
        ("tenancy", "0091_merge_upstream_122"),
    ]

    operations = [
        migrations.RunPython(
            backfill_legacy_max_lifecycle,
            migrations.RunPython.noop,
        ),
    ]
