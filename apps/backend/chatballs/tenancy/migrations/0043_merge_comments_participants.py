"""Apply both histories' tenant guards without rewriting accepted migrations."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0042_comment_guards"),
        ("tenancy", "0042_participant_guards"),
        ("conversations", "0032_merge_comments_participants"),
    ]

    operations = []
