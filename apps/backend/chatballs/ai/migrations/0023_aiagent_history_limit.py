from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0022_release_agent_model_from_integration"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiagent",
            name="history_limit",
            field=models.PositiveSmallIntegerField(default=20),
        ),
    ]
