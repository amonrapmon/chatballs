"""Keep the accepted quality schema alongside support reporting history."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0032_quality_data"),
        ("conversations", "0036_status_stop_boundary"),
    ]

    operations = []
