from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0039_remove_organization_currency"),
    ]

    operations = [
        migrations.AddField(
            model_name="instancesettings",
            name="public_port",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
    ]
