"""Source-scoped media announcement identity with native Message storage."""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("conversations", "0052_message_connector_origin")]

    operations = [
        migrations.AddField(
            model_name="message",
            name="connector_media",
            field=models.JSONField(default=dict, blank=True),
        ),
        migrations.CreateModel(
            name="ConnectorMediaIngest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_chat_id", models.CharField(max_length=128)),
                ("external_message_id", models.CharField(max_length=128)),
                ("part_index", models.PositiveSmallIntegerField(default=0)),
                ("announce_event_id", models.CharField(max_length=256)),
                ("announce_fingerprint", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("integration", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="connector_media_ingests", to="integrations.integration")),
                ("message", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="connector_media_ingest", to="conversations.message")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization")),
            ],
            options={
                "indexes": [models.Index(fields=["organization", "integration"], name="conv_media_tenant_route")],
                "constraints": [
                    models.UniqueConstraint(fields=["integration", "external_chat_id", "external_message_id", "part_index"], name="uniq_connector_media_source_part"),
                    models.CheckConstraint(condition=models.Q(part_index=0), name="connector_media_v1_single_part"),
                ],
            },
        ),
    ]
