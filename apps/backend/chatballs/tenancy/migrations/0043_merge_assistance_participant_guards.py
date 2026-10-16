"""Join the independent assistance and participant migration branches."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0041_reply_assistance_guards"),
        ("tenancy", "0042_participant_guards"),
    ]

    operations = []
