"""Quality data only; no default criteria or retroactive analyses."""

import django.db.models.deletion
from django.db import migrations, models


def identity_fields():
    return [
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization")),
    ]


class Migration(migrations.Migration):
    dependencies = [("conversations", "0031_participant_data"), ("identity", "0042_organization_participant_limit")]

    operations = [
        migrations.CreateModel(
            name="QualityCriteriaVersion",
            fields=identity_fields() + [
                ("version", models.PositiveIntegerField()),
                ("criteria", models.JSONField()),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="identity.organizationmembership")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"constraints": [
                models.UniqueConstraint(fields=["organization", "version"], name="quality_criteria_version"),
                models.CheckConstraint(condition=models.Q(version__gt=0), name="quality_criteria_positive"),
            ]},
        ),
        migrations.CreateModel(
            name="QualitySettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("organization", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to="identity.organization")),
                ("enabled", models.BooleanField(default=False)),
                ("current_version", models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to="conversations.qualitycriteriaversion")),
            ],
            options={"constraints": [models.CheckConstraint(
                condition=models.Q(enabled=False) | models.Q(current_version__isnull=False), name="quality_enabled_requires_criteria",
            )]},
        ),
        migrations.CreateModel(
            name="QualityJob",
            fields=identity_fields() + [
                ("conversation", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="conversations.conversation")),
                ("completion_event_id", models.UUIDField()),
                ("completed_at", models.DateTimeField()),
                ("criteria_version", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="conversations.qualitycriteriaversion")),
                ("history_revision", models.CharField(max_length=64)),
                ("history_snapshot", models.JSONField()),
                ("revision", models.PositiveIntegerField()),
                ("operation_id", models.UUIDField()),
                ("state", models.CharField(choices=[("WAITING", "Waiting"), ("RUNNING", "Running"), ("SUCCEEDED", "Succeeded"), ("FAILED", "Failed")], default="WAITING", max_length=16)),
                ("error_code", models.CharField(blank=True, max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("started_at", models.DateTimeField(null=True)),
                ("finished_at", models.DateTimeField(null=True)),
            ],
            options={
                "indexes": [models.Index(fields=["organization", "state", "created_at"], name="quality_job_queue")],
                "constraints": [
                    models.UniqueConstraint(fields=["organization", "operation_id"], name="quality_job_operation"),
                    models.UniqueConstraint(fields=["conversation", "completion_event_id", "revision"], name="quality_job_revision"),
                    models.CheckConstraint(condition=models.Q(revision__gt=0), name="quality_job_positive"),
                    models.CheckConstraint(condition=models.Q(state__in=["WAITING", "RUNNING", "SUCCEEDED", "FAILED"]), name="quality_job_state"),
                    models.CheckConstraint(condition=(
                        models.Q(state="WAITING", started_at__isnull=True, finished_at__isnull=True, error_code="")
                        | models.Q(state="RUNNING", started_at__isnull=False, finished_at__isnull=True, error_code="")
                        | models.Q(state="SUCCEEDED", started_at__isnull=False, finished_at__isnull=False, error_code="")
                        | (models.Q(state="FAILED", started_at__isnull=False, finished_at__isnull=False) & ~models.Q(error_code=""))
                    ), name="quality_job_state_details"),
                    models.CheckConstraint(condition=models.Q(finished_at__isnull=True)
                        | models.Q(finished_at__gte=models.F("started_at")), name="quality_job_time_order"),
                ],
            },
        ),
        migrations.CreateModel(
            name="QualityResult",
            fields=identity_fields() + [
                ("job", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="result", to="conversations.qualityjob")),
                ("data", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name="QualityJobOperation",
            fields=identity_fields() + [
                ("operation_id", models.UUIDField()),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="conversations.qualityjob")),
            ],
            options={"constraints": [models.UniqueConstraint(
                fields=["organization", "operation_id"], name="quality_operation_alias",
            )]},
        ),
        migrations.CreateModel(
            name="QualityCorrection",
            fields=identity_fields() + [
                ("result", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="corrections", to="conversations.qualityresult")),
                ("revision", models.PositiveIntegerField()),
                ("criterion_code", models.SlugField(max_length=64)),
                ("value", models.JSONField()),
                ("author", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="identity.organizationmembership")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reason", models.TextField()),
            ],
            options={"ordering": ["revision"], "constraints": [
                models.UniqueConstraint(fields=["result", "revision"], name="quality_correction_revision"),
                models.CheckConstraint(condition=models.Q(revision__gt=0), name="quality_correction_positive"),
                models.CheckConstraint(condition=~models.Q(reason=""), name="quality_correction_reason"),
            ]},
        ),
    ]
