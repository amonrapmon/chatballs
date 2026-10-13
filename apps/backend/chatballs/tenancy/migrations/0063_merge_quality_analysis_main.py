"""Keep quality cleanup guards alongside the current tenant migration graph."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0049_quality_conversation_purge"),
        ("tenancy", "0062_merge_ratings_mail_support"),
        ("conversations", "0043_merge_quality_analysis_main"),
    ]
    operations = []
