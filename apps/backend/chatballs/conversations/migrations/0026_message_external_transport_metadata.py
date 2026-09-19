from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0025_contact_avatar_contact_avatar_content_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="external_occurred_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="message",
            name="external_reply_to_id",
            field=models.CharField(blank=True, default="", max_length=128),
        ),
    ]
