"""Join mail data with the current conversation migration history."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0032_email_continuation_data"),
        ("conversations", "0034_merge_template_libraries"),
    ]
    operations = []
