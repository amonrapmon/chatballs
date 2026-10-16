from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("conversations", "0034_email_thread_followup")]
    # Existing mail has no trustworthy historical sender snapshot. Leave it
    # absent rather than reconstructing history from today's mailbox settings.
    operations = [
        migrations.AddField(model_name="emailthreadmessage", name="sender_address",
                            field=models.EmailField(blank=True, default="", max_length=254)),
        migrations.AddField(model_name="emailthreadmessage", name="recipient_address",
                            field=models.EmailField(blank=True, default="", max_length=254)),
        migrations.AddField(model_name="emailthreadmessage", name="subject",
                            field=models.CharField(blank=True, default="", max_length=998)),
        migrations.AddField(model_name="emailthreadmessage", name="mailbox_name",
                            field=models.CharField(blank=True, default="", max_length=255)),
    ]
