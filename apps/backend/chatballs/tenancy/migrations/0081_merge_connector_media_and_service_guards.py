"""Join API Connector media RLS with the 1.20 service guard chain."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0068_connector_media_rls"),
        ("tenancy", "0080_site_event_guards"),
    ]

    operations = []
