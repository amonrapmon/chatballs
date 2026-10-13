"""Keep collaboration history alongside published availability/mail dependencies."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0035_comment_parent_delete"),
        ("conversations", "0035_merge_email_continuation"),
    ]
    operations = []
