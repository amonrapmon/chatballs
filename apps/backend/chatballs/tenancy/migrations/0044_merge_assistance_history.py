"""Join assistance guards with the accepted internal histories' guards."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0041_reply_assistance_guards"),
        ("tenancy", "0043_merge_comments_participants"),
    ]

    operations = []
