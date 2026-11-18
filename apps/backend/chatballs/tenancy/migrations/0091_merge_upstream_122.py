"""Join upstream external-agent tenant guards with fork Connector RLS.

Both lines are independently applied before this no-op merge node.
"""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0082_merge_20261106_0021"),
        ("tenancy", "0090_external_notice_guards"),
    ]

    operations = []
