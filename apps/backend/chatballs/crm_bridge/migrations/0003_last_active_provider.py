"""Remember provider identity when CRM is temporarily disabled."""

from django.db import migrations, models


def backfill_last_provider(apps, schema_editor):
    config = apps.get_model("crm_bridge", "CRMOrganizationConfig")
    for row in config.objects.exclude(provider="NONE").iterator():
        row.last_active_provider = row.provider
        row.save(update_fields=["last_active_provider"])


class Migration(migrations.Migration):
    dependencies = [("crm_bridge", "0002_tenant_guards")]

    operations = [
        migrations.AddField(
            model_name="crmorganizationconfig",
            name="last_active_provider",
            field=models.CharField(
                max_length=16,
                default="NONE",
                choices=[("NONE", "None"), ("YCLIENTS", "YCLIENTS"), ("DIKIDI", "DIKIDI")],
            ),
        ),
        migrations.RunPython(backfill_last_provider, migrations.RunPython.noop),
    ]
