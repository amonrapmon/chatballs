"""Initial UNAVAILABLE has no start time; historical work is unknown."""

import django.db.models.deletion
from django.db import migrations, models

STATUSES = [(code, code.title()) for code in ("READY", "BUSY", "BREAK", "UNAVAILABLE")]


class Migration(migrations.Migration):
    dependencies = [("identity", "0041_instance_tools_private_network")]
    operations = [
        migrations.AddField(
            model_name="organizationmembership", name="work_status",
            field=models.CharField(choices=STATUSES, max_length=16, default="UNAVAILABLE", db_default="UNAVAILABLE"),
        ),
        migrations.AddField(
            model_name="organizationmembership", name="work_status_version",
            field=models.PositiveBigIntegerField(default=0, db_default=0),
        ),
        migrations.AddField(
            model_name="organizationmembership", name="work_status_changed_at",
            field=models.DateTimeField(null=True, blank=True, db_default=None),
        ),
        migrations.AddConstraint(
            model_name="organizationmembership",
            constraint=models.CheckConstraint(condition=models.Q(work_status__in=[code for code, _ in STATUSES]), name="membership_work_status_valid"),
        ),
        migrations.AddConstraint(
            model_name="organizationmembership",
            constraint=models.CheckConstraint(condition=models.Q(work_status_version=0, work_status_changed_at__isnull=True, work_status="UNAVAILABLE") | models.Q(work_status_version__gt=0, work_status_changed_at__isnull=False), name="membership_work_status_initial"),
        ),
        migrations.CreateModel(
            name="WorkStatusOperation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("operation_id", models.UUIDField()),
                ("previous_status", models.CharField(choices=STATUSES, max_length=16)),
                ("status", models.CharField(choices=STATUSES, max_length=16)),
                ("version", models.PositiveBigIntegerField()),
                ("changed_at", models.DateTimeField(null=True)),
                ("recorded_at", models.DateTimeField()),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="+", to="identity.organization")),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="work_status_operations", to="identity.organizationmembership")),
            ],
            options={
                "ordering": ["version", "id"],
                "indexes": [models.Index(fields=["organization", "membership", "version"], name="work_status_history_idx")],
                "constraints": [
                    models.UniqueConstraint(fields=["membership", "operation_id"], name="uniq_work_status_operation"),
                    models.UniqueConstraint(fields=["membership", "version"], condition=~models.Q(previous_status=models.F("status")), name="uniq_work_status_transition"),
                    models.CheckConstraint(condition=models.Q(status__in=[code for code, _ in STATUSES], previous_status__in=[code for code, _ in STATUSES]), name="work_status_operation_valid"),
                    models.CheckConstraint(condition=models.Q(version=0, changed_at__isnull=True, status="UNAVAILABLE", previous_status="UNAVAILABLE") | models.Q(version__gt=0, changed_at__isnull=False), name="work_status_operation_initial"),
                    models.CheckConstraint(condition=models.Q(previous_status=models.F("status")) | models.Q(changed_at=models.F("recorded_at"), version__gt=0), name="work_status_transition_time"),
                ],
            },
        ),
    ]
