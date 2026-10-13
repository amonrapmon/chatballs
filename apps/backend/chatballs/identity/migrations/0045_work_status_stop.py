from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("identity", "0044_merge_work_status_supervisor"),
        ("tenancy", "0046_merge_domain_event_guards"),
    ]
    operations = [
        migrations.AddField(model_name="workstatusoperation", name="stopped_at",
                            field=models.DateTimeField(null=True, editable=False)),
        migrations.AddConstraint(model_name="workstatusoperation", constraint=models.CheckConstraint(
            condition=models.Q(stopped_at__isnull=True) | models.Q(stopped_at__gte=models.F("changed_at")),
            name="work_status_stop_time",
        )),
    ]
