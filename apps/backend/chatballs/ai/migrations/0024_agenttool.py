"""Инструменты внешних серверов, включённые агенту (SPEC-0023 R-9)."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0023_aiagent_history_limit"),
        ("integrations", "0012_integration_tools_snapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="AgentTool",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tool_name", models.CharField(blank=True, max_length=128)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "agent",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="tools", to="ai.aiagent"
                    ),
                ),
                (
                    "integration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="agent_tools",
                        to="integrations.integration",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization"
                    ),
                ),
            ],
            options={
                "ordering": ["integration_id", "tool_name"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("agent", "integration", "tool_name"), name="uniq_agent_tool"
                    )
                ],
            },
        ),
    ]
