import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("conversations", "0046_merge_email_ui_rules")]

    operations = [
        migrations.AddField(model_name="message", name="format_version",
                            field=models.PositiveSmallIntegerField(default=0)),
        migrations.AddField(model_name="message", name="presentation",
                            field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="message", name="delivery_representation",
                            field=models.CharField(blank=True, default="", max_length=8)),
        migrations.AddField(model_name="message", name="template_snapshot",
                            field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="message", name="ai_delivery",
                            field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="message", name="ai_reply_to",
                            field=models.OneToOneField(blank=True, null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="ai_reply", to="conversations.message")),
    ]
