"""Only new data: do not reconstruct transfers from existing assignments."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0029_tool_called_event"),
        ("identity", "0041_instance_tools_private_network"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TransferReason",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=64)),
                ("name", models.CharField(max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="identity.organization")),
            ],
            options={
                "ordering": ["code", "id"],
                "constraints": [models.UniqueConstraint(fields=("organization", "code"), name="uniq_transfer_reason_org_code")],
            },
        ),
        migrations.CreateModel(
            name="ConversationTransfer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                ("operation_id", models.UUIDField()),
                ("reason_code", models.SlugField(max_length=64)),
                ("reason_name", models.CharField(max_length=120)),
                ("comment", models.TextField(blank=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization")),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transfers", to="conversations.conversation")),
                ("reason", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transfers", to="conversations.transferreason")),
                ("previous_operator", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("new_operator", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("initiated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-occurred_at", "-id"],
                "indexes": [models.Index(fields=["organization", "conversation", "-occurred_at", "-id"], name="transfer_history_idx")],
                "constraints": [models.UniqueConstraint(fields=("organization", "operation_id"), name="uniq_transfer_org_operation")],
            },
        ),
    ]
