"""Align implicit Django BigAutoField metadata with the model state.

The initial CRM migration declared equivalent SQL primary keys but omitted
Django's implicit auto_created and verbose_name field attributes.
This is a migration-state alignment; it does not change key types or values.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("crm_bridge", "0004_binding_integration_cascade"),
    ]

    operations = [
        migrations.AlterField(
            model_name="crmcompany",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
        migrations.AlterField(
            model_name="crmconnectionbinding",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
        migrations.AlterField(
            model_name="crmorganizationconfig",
            name="id",
            field=models.BigAutoField(
                auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
            ),
        ),
    ]
