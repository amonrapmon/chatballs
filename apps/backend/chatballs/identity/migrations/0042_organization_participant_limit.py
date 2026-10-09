"""The owner-selected default applies without altering any conversation."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("identity", "0041_instance_tools_private_network")]
    operations = [
        migrations.AddField(
            model_name="organization",
            name="additional_participant_limit",
            field=models.PositiveIntegerField(default=5, db_default=5),
        ),
    ]
