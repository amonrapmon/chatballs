"""Create only new comments; existing notes and messages remain untouched."""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0030_transfer_data"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ConversationComment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("audience", models.CharField(choices=[("INTERNAL", "INTERNAL")], max_length=16)),
                ("text", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("operation_id", models.UUIDField()),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization")),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="comments", to="conversations.conversation")),
                ("author", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["created_at", "id"],
                "indexes": [models.Index(fields=["organization", "conversation", "audience", "created_at", "id"], name="conv_comment_window")],
                "constraints": [
                    models.CheckConstraint(condition=models.Q(audience="INTERNAL"), name="conv_comment_internal_only"),
                    models.CheckConstraint(condition=models.Q(text__regex=r"\S"), name="conv_comment_text_required"),
                    models.UniqueConstraint(fields=("organization", "operation_id"), name="uniq_comment_org_operation"),
                ],
            },
        ),
    ]
