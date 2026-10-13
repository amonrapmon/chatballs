import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("conversations", "0033_merge_domain_events_email")]
    operations = [migrations.AddField(
        model_name="emailthread", name="previous_thread",
        field=models.ForeignKey(
            to="conversations.emailthread", null=True, blank=True,
            on_delete=django.db.models.deletion.SET_NULL, related_name="followups",
        ),
    )]
