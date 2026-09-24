# ADR-CHATBALLS-0042 §3: BYOK — единственный режим; поле credential_mode больше не нужно.
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0015_backfill_channel_agents"),
    ]
    operations = [
        migrations.RemoveField(
            model_name="aiagent",
            name="credential_mode",
        ),
    ]
