"""Снимок инструментов MCP-сервера и код последней ошибки (SPEC-0023 R-2, R-5)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0011_integration_external_server"),
    ]

    operations = [
        migrations.AddField(
            model_name="integration",
            name="last_error_code",
            field=models.CharField(blank=True, max_length=32),
        ),
        migrations.AddField(
            model_name="integration",
            name="tools",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="integration",
            name="tools_refreshed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
