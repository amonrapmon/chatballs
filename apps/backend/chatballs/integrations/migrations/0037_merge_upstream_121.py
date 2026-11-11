"""Join API Connector/Gateway history with upstream Chatballs 1.21 scenarios.

Both migration paths originate from integrations.0033, but the fork already
uses its own 0034..0036 lineage. Do not rewrite applied migrations.
"""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0036_alter_integration_provider"),
        ("integrations", "0034_scenario_category_path"),
    ]

    operations = []
