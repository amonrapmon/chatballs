"""Keep reply assistance and turn diagnostics in one migration graph."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0025_turndiagnostic"),
        ("ai", "0026_reply_suggestion_send"),
    ]

    operations = []
