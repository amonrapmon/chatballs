"""Keep both independently accepted conversation data migrations."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0032_domain_event_data"),
        ("conversations", "0032_email_continuation_data"),
    ]
    operations = []
