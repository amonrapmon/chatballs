"""Snapshot the authenticated source user ID for connector conversations."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("conversations", "0047_message_reply_snapshot")]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="route_external_user_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
        migrations.AddIndex(
            model_name="conversation",
            index=models.Index(
                fields=["connection", "contact", "external_chat_id", "lifecycle"],
                name="conv_source_route",
            ),
        ),
    ]
