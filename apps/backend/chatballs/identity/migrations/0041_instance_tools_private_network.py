import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0040_instance_public_port"),
    ]

    operations = [
        migrations.AddField(
            model_name="instancesettings",
            name="tools_private_network",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="instancesettings",
            name="tools_private_network_enabled_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="instancesettings",
            name="tools_private_network_enabled_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
