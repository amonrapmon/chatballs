import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("identity", "0043_supervisor"),
        ("conversations", "0032_domain_event_data"),
    ]
    operations = [
        migrations.CreateModel(
            name="RatingSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=False)),
                ("scale", models.JSONField(blank=True, default=list)),
                ("text", models.TextField(blank=True, default="")),
                ("delay_seconds", models.PositiveIntegerField(default=0)),
                ("organization", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to="identity.organization")),
            ],
        ),
        migrations.CreateModel(
            name="RatingRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("public_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("scale", models.JSONField()),
                ("text", models.TextField()),
                ("delay_seconds", models.PositiveIntegerField()),
                ("responder_ids", models.JSONField(default=list)),
                ("delivery_session_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("due_at", models.DateTimeField()),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
                ("credential_hash", models.CharField(blank=True, max_length=64, null=True, unique=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization")),
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="conversations.conversation")),
                ("completion", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to="conversations.conversationevent")),
            ],
            options={
                "indexes": [models.Index(fields=["organization", "due_at"], name="rating_due_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=["conversation", "completion"], name="rating_completion_unique"),
                    models.CheckConstraint(
                        condition=models.Q(sent_at__isnull=True, credential_hash__isnull=True, expires_at__isnull=True)
                        | models.Q(sent_at__isnull=False, credential_hash__isnull=False, expires_at__isnull=False),
                        name="rating_credential_lifecycle",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="CustomerRating",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("value", models.CharField(max_length=64)),
                ("comment", models.CharField(blank=True, default="", max_length=2000)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization")),
                ("request", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="result", to="ratings.ratingrequest")),
            ],
        ),
    ]
