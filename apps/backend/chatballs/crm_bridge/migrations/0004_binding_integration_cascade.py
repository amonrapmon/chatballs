"""Deleting a messenger integration must not be blocked by an obsolete CRM mapping."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm_bridge", "0003_last_active_provider")]

    operations = [
        migrations.AlterField(
            model_name="crmconnectionbinding",
            name="integration",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="crm_bridge_binding",
                to="integrations.integration",
            ),
        ),
    ]
